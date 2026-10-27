"""Compact session (không gọi model): kích hoạt, giữ đuôi, không mồ côi ToolMessage, cộng dồn, an toàn khi lỗi.

Chạy riêng và in bản tóm tắt:  pytest tests/test_compact.py -v -s
"""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import compact
import paths
from compact import SUMMARY_PREFIX, compact_messages, compaction_reasons, should_compact, split_history, total_chars
from config import COMPACT_KEEP_LAST, COMPACT_TRIGGER_CHARS
from tool_result_budget import _excerpt
from tools.files import _read, read_log_time_range

BIG_LOG = "ERROR DB_POOL_EXHAUSTED " * 2000
SUMMARY_MAX_CHARS = 4800


def make_history(turns: int = 5):
    msgs = []
    for i in range(turns):
        msgs += [
            HumanMessage(content=f"Câu hỏi {i}"),
            AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"path": "data/server.log"}, "id": f"c{i}"}]),
            ToolMessage(content=BIG_LOG, tool_call_id=f"c{i}", name="read_file"),
            AIMessage(content=f"Trả lời {i}: lỗi DB_POOL_EXHAUSTED"),
        ]
    return msgs


def assert_no_orphan_tool_messages(messages):
    seen_calls = set()
    for m in messages:
        if isinstance(m, AIMessage):
            seen_calls |= {c["id"] for c in m.tool_calls}
        if isinstance(m, ToolMessage):
            assert m.tool_call_id in seen_calls, f"ToolMessage mồ côi: {m.tool_call_id}"


# ---------------------------------------------------------------- cơ bản


def test_trigger_threshold():
    history = make_history(2)
    assert should_compact(history, 1000)
    assert not should_compact(history, total_chars(history) + 1)
    assert "context_threshold" in compaction_reasons(history, 1000)
    assert compaction_reasons(history[:1], 1000, milestone=True) == ["milestone"]
    assert compaction_reasons(history[:1], 1000, cold_start=True) == ["cold_start"]


def test_split_does_not_orphan_tool_messages():
    history = make_history(5)
    for keep in range(1, len(history)):
        old, tail = split_history(history, keep)
        assert old + tail == history
        assert not tail or isinstance(tail[0], HumanMessage)
        assert_no_orphan_tool_messages(tail)


def test_split_honors_keep_last_and_falls_back_to_last_turn():
    history = make_history(5)  # 4 message/lượt
    old, tail = split_history(history, 8)
    assert len(tail) >= 8 and isinstance(tail[0], HumanMessage)
    old, tail = split_history(history, 999)  # không lượt nào đủ dài -> giữ đúng lượt cuối
    assert tail == history[-4:]


def test_compact_replaces_old_with_summary_and_keeps_tail():
    history = make_history(5)
    new, report = compact_messages(history, keep_last=4)
    assert report["compacted"] is True
    assert report["after_chars"] < report["before_chars"]
    assert new[0].text.startswith(SUMMARY_PREFIX) and "DB_POOL_EXHAUSTED" in new[0].text
    assert new[1:] == history[-4:]
    assert isinstance(new[1], HumanMessage)
    assert BIG_LOG not in "".join(m.text for m in new[:-4])  # log lớn của lượt cũ không còn trong context
    assert_no_orphan_tool_messages(new)


def test_compact_skips_when_nothing_old():
    history = make_history(1)
    new, report = compact_messages(history, keep_last=10)
    assert new == history and report["compacted"] is False


def test_compact_skips_when_old_part_is_only_a_summary():
    history = [HumanMessage(content=SUMMARY_PREFIX + "## Mục tiêu / yêu cầu và quyết định người dùng\n- x\n"),
               HumanMessage(content="Câu mới"), AIMessage(content="ok")]
    new, report = compact_messages(history, keep_last=2)
    assert new == history and report["compacted"] is False


def test_compact_keeps_history_when_something_breaks(monkeypatch):
    history = make_history(4)

    def boom(*args, **kwargs):
        raise RuntimeError("hỏng bất ngờ")

    monkeypatch.setattr(compact, "_compact", boom)
    new, report = compact_messages(history, keep_last=4)
    assert new == history
    assert report["compacted"] is False and "RuntimeError" in report["reason"]


# ---------------------------------------------------------------- kịch bản điều tra log thật (5 prompt trong README)


def investigation_history(lab_dirs):
    """Dựng đúng history mà agent tạo ra khi chạy 5 prompt: kết quả read_file bị cắt, read_log_time_range là text thô."""
    raw = _read(paths.WORKSPACE_DIR, "data/server.log")["content"]
    excerpt = json.dumps({"ok": True, "path": "data/server.log", "truncated": True, "content": _excerpt(raw, 1300)}, ensure_ascii=False)
    window = read_log_time_range.invoke({"path": "data/server.log", "start_time": "13:39", "end_time": "13:41"})
    call = lambda name, args, i: AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": i}])
    return [
        HumanMessage(content="Đọc data/server.log, tìm lỗi chính."),
        call("read_file", {"path": "data/server.log"}, "c1"),
        ToolMessage(content=excerpt, tool_call_id="c1", name="read_file"),
        AIMessage(content="Lỗi chính là DB_POOL_EXHAUSTED ở module payment: QueuePool limit of size 10 reached."),
        HumanMessage(content="Lỗi xuất hiện lúc mấy giờ, module nào?"),
        AIMessage(content="Lỗi đầu tiên lúc 13:37:12, module payment (cảnh báo pool 10/10 từ 13:37:08)."),
        HumanMessage(content="Mình đã thử tăng pool size lên 20 nhưng vẫn lỗi, ghi nhớ giúp, thử hướng khác."),
        call("save_memory", {"note": "Đã tăng pool size lên 20 nhưng vẫn lỗi DB_POOL_EXHAUSTED"}, "c2"),
        ToolMessage(content='{"ok": true, "status": "created", "id": "abc123"}', tool_call_id="c2", name="save_memory"),
        AIMessage(content="Đã ghi nhớ. Hướng khác: kiểm tra connection leak."),
        HumanMessage(content="Đọc lại log đoạn 13:39–13:41 xem có gì khác."),
        call("read_log_time_range", {"path": "data/server.log", "start_time": "13:39", "end_time": "13:41"}, "c3"),
        ToolMessage(content=window, tool_call_id="c3", name="read_log_time_range"),
        AIMessage(content="Khác: 13:40:00 job nightly_settlement giữ 7 connection 410s, nghi thiếu conn.close() ở settlement.py:88."),
        HumanMessage(content="Tóm lại mình đang điều tra lỗi gì, đã thử gì, bước tiếp theo là gì?"),
        AIMessage(content="Đang điều tra DB_POOL_EXHAUSTED (payment). Đã thử pool 20. Tiếp theo: sửa leak ở settlement.py:88."),
        HumanMessage(content="Cảm ơn."),
        AIMessage(content="Không có gì."),
    ]


FACTS = [
    "DB_POOL_EXHAUSTED",
    "payment",
    "13:37:12",  # giờ lỗi đầu tiên
    "pool size lên 20",  # điều đã thử
    "settlement.py:88",  # nguyên nhân nghi ngờ
    "nightly_settlement",
    "13:40:00",
]


def test_investigation_scenario_keeps_key_facts(lab_dirs, capsys):
    history = investigation_history(lab_dirs)
    reasons = compaction_reasons(history, COMPACT_TRIGGER_CHARS)
    assert reasons, "kịch bản 5 prompt phải kích hoạt compact"

    new, report = compact_messages(history, keep_last=2)
    assert report["compacted"] is True
    summary = new[0].text
    missing = [f for f in FACTS if f not in summary]
    assert not missing, f"summary làm rơi: {missing}\n{summary}"
    assert len(summary) <= SUMMARY_MAX_CHARS
    assert new[1:] == history[-2:]
    assert_no_orphan_tool_messages(new)
    with capsys.disabled():
        print(f"\n--- compact: {report['before_chars']} -> {report['after_chars']} ký tự, "
              f"{report['messages_before']} -> {report['messages_after']} messages ---\n{summary}")


def test_repeated_compaction_accumulates_without_nesting(lab_dirs):
    history = investigation_history(lab_dirs)
    first, _ = compact_messages(history, keep_last=2)
    more = [
        HumanMessage(content="Đọc lại data/server.log đoạn 13:37–13:38."),
        AIMessage(content="", tool_calls=[{"name": "read_log_time_range", "args": {"path": "data/server.log", "start_time": "13:37", "end_time": "13:38"}, "id": "c9"}]),
        ToolMessage(content=read_log_time_range.invoke({"path": "data/server.log", "start_time": "13:37", "end_time": "13:38"}), tool_call_id="c9", name="read_log_time_range"),
        AIMessage(content="Đoạn này chỉ có lỗi pool, không có leak."),
        HumanMessage(content="Ghi chú tiếp."),
        AIMessage(content="Ok."),
    ]
    second, report = compact_messages(first + more, keep_last=2)
    assert report["compacted"] is True
    summary = second[0].text
    assert summary.count(SUMMARY_PREFIX.strip()) == 1, "summary bị lồng nhau"
    missing = [f for f in FACTS if f not in summary]
    assert not missing, f"compact lần 2 làm rơi: {missing}\n{summary}"
    assert len(summary) <= SUMMARY_MAX_CHARS
    assert_no_orphan_tool_messages(second)


def test_evidence_is_grouped_by_template_with_count_and_time_range(lab_dirs):
    history = investigation_history(lab_dirs)
    new, _ = compact_messages(history, keep_last=2)
    pool_lines = [l for l in new[0].text.splitlines() if l.startswith("- ") and "QueuePool limit" in l and "txn_id" in l]
    assert len(pool_lines) == 1  # hàng chục dòng lỗi giống nhau chỉ còn một dòng
    assert "×" in pool_lines[0] and "→" in pool_lines[0]