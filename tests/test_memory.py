"""Memory: lưu, chống trùng (kể cả gần giống), cập nhật, quên, file hỏng, giới hạn inject."""

import json

import pytest

import paths
from tools import memory
from tools.memory import MAX_INJECT_CHARS, clear_memory, forget_memory, load_memory, save_memory


def save(note):
    return json.loads(save_memory.invoke({"note": note}))


def forget(query):
    return json.loads(forget_memory.invoke({"query": query}))


def notes():
    return json.loads(memory._file().read_text(encoding="utf-8"))["notes"]


POOL = "User đã tăng pool size lên 20 nhưng vẫn gặp lỗi DB_POOL_EXHAUSTED trong module payment; cần thử hướng khác."


def test_save_then_load_and_exact_duplicate(lab_dirs):
    first = save("Người dùng thích câu trả lời ngắn gọn")
    assert first["status"] == "created"
    again = save("người dùng thích câu trả lời ngắn gọn!")
    assert again == {"ok": True, "status": "duplicate", "id": first["id"], "existing": "Người dùng thích câu trả lời ngắn gọn"}
    assert "ngắn gọn" in load_memory() and len(notes()) == 1


def test_near_duplicates_from_repeated_runs_collapse_to_one_note(lab_dirs):
    variants = [
        POOL,
        POOL.replace("EXHAUSTED", "EXHAUSTD"),  # sai chính tả
        POOL.replace(";", ","),  # khác dấu câu
        "User đã tăng pool size lên 20 nhưng vẫn gặp lỗi DB_POOL_EXHAUSTED, cần thử hướng khác.",  # thiếu 'trong module payment'
        "Đã tăng pool size lên 20 nhưng vẫn gặp lỗi DB_POOL_EXHAUSTED, cần thử hướng khác.",  # thiếu 'User'
    ]
    statuses = [save(v)["status"] for v in variants]
    assert statuses == ["created", "duplicate", "duplicate", "duplicate", "duplicate"]
    assert len(notes()) == 1 and notes()[0]["text"] == POOL


def test_more_detailed_note_replaces_the_shorter_one(lab_dirs):
    short = save("Đã tăng pool size lên 20 nhưng vẫn gặp lỗi DB_POOL_EXHAUSTED, cần thử hướng khác.")
    result = save(POOL)
    assert result["status"] == "updated" and result["id"] == short["id"]
    assert [n["text"] for n in notes()] == [POOL]


def test_different_number_is_new_information_not_duplicate(lab_dirs):
    save(POOL)
    assert save(POOL.replace("lên 20", "lên 50"))["status"] == "created"
    assert len(notes()) == 2


def test_short_notes_need_exact_match(lab_dirs):
    save("User tên là An")
    assert save("User tên là Ân")["status"] == "created"


def test_empty_and_too_long_notes_rejected(lab_dirs):
    assert json.loads(save_memory.invoke({"note": "   "}))["error"]["code"] == "EMPTY_NOTE"
    assert json.loads(save_memory.invoke({"note": "x" * 301}))["error"]["code"] == "NOTE_TOO_LONG"
    assert not memory._file().exists()


def test_forget_by_id_phrase_ambiguous_and_missing(lab_dirs):
    a = save("Người dùng làm việc bằng tiếng Việt")["id"]
    save("Người dùng dùng Windows và VS Code")
    assert forget("zz")["error"]["code"] == "QUERY_TOO_SHORT"
    assert forget("không tồn tại")["error"]["code"] == "NOT_FOUND"
    ambiguous = forget("người dùng")
    assert ambiguous["error"]["code"] == "AMBIGUOUS_QUERY" and len(ambiguous["error"]["candidates"]) == 2
    assert forget(a) == {"ok": True, "removed": "Người dùng làm việc bằng tiếng Việt"}
    assert forget("windows")["ok"] is True
    assert forget("windows")["error"]["code"] == "MEMORY_EMPTY" or forget("windows")["error"]["code"] == "NOT_FOUND"


def test_corrupt_file_is_reported_and_never_overwritten(lab_dirs):
    f = memory._file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{không phải json", encoding="utf-8")
    assert load_memory() == ""
    assert json.loads(save_memory.invoke({"note": "một ghi chú hợp lệ"}))["error"]["code"] == "MEMORY_CORRUPT"
    assert json.loads(forget_memory.invoke({"query": "ghi chú"}))["error"]["code"] == "MEMORY_CORRUPT"
    assert f.read_text(encoding="utf-8") == "{không phải json"


def test_load_memory_keeps_newest_notes_and_never_cuts_a_note(lab_dirs):
    for i in range(60):
        save(f"Ghi chú số {i:02d}: " + "nội dung khác nhau hoàn toàn " * 3 + chr(65 + i % 26) * 5 + str(i))
    text = load_memory()
    assert len(text) <= MAX_INJECT_CHARS
    assert "số 59" in text and "số 00" not in text
    assert all(line.startswith("- (") for line in text.splitlines())


def test_clear_memory(lab_dirs):
    save("Người dùng thích bảng so sánh")
    assert clear_memory() is True and clear_memory() is False
    assert load_memory() == ""