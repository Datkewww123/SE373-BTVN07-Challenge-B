from __future__ import annotations

import json
import re
import uuid
from datetime import date
from difflib import SequenceMatcher

from langchain_core.tools import tool

import paths

MAX_NOTE_CHARS = 300
MAX_INJECT_CHARS = 4000
MIN_QUERY_CHARS = 3
# Ghi chú gần giống nhau (sai chính tả, khác dấu câu, thêm/bớt vài từ) bị coi là trùng.
SIMILARITY = 0.85
MIN_FUZZY_CHARS = 40  # ghi chú ngắn chỉ trùng khi giống hệt, tránh nuốt nhầm 'tên là An' vs 'tên là Ân'


class MemoryCorrupt(Exception):
    pass


def _file():
    return paths.WORKSPACE_DIR / paths.MEMORY_SUBDIR / "memory.json"


def _err(code: str, message: str, **extra) -> str:
    return json.dumps({"ok": False, "error": {"code": code, "message": message, **extra}}, ensure_ascii=False)


def _read() -> list[dict]:
    f = _file()
    if not f.exists():
        return []
    try:
        notes = json.loads(f.read_text(encoding="utf-8"))["notes"]
        if not isinstance(notes, list):
            raise ValueError("notes không phải list")
        return notes
    except (ValueError, KeyError, TypeError) as exc:
        raise MemoryCorrupt(str(exc)) from exc


def _write(notes: list[dict]) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps({"version": 1, "notes": notes}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(f)


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def _same_note(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    if min(len(na), len(nb)) < MIN_FUZZY_CHARS:
        return False
    if re.findall(r"\d+", na) != re.findall(r"\d+", nb):
        return False  # khác số (pool 20 vs 50) là thông tin mới, không phải trùng
    return SequenceMatcher(None, na, nb).ratio() >= SIMILARITY


def _render(note: dict) -> str:
    return f"- ({note['id']}) [{note['created']}] {note['text']}"


def load_memory() -> str:
    """Text để inject vào system prompt: giữ các ghi chú mới nhất, không cắt giữa ghi chú."""
    try:
        notes = _read()
    except MemoryCorrupt:
        return ""
    kept, size = [], 0
    for note in reversed(notes):
        line = _render(note)
        if size + len(line) + 1 > MAX_INJECT_CHARS:
            break
        kept.append(line)
        size += len(line) + 1
    return "\n".join(reversed(kept))


@tool
def save_memory(note: str) -> str:
    """Lưu MỘT ghi chú ngắn về người dùng để nhớ cho các cuộc trò chuyện sau.

    Chỉ lưu thông tin ổn định, hữu ích lâu dài (sở thích, vai trò, quy ước làm việc).
    Không lưu bí mật/API key, dữ liệu một lần, hay nội dung có thể đọc lại từ file.
    Ghi chú gần giống ghi chú đã có thì không tạo bản mới: "duplicate" (giữ bản cũ) hoặc "updated" (bản mới đầy đủ hơn
    nên thay bản cũ). Nếu existing/previous mâu thuẫn với điều người dùng vừa nói, hãy forget_memory rồi save_memory lại.
    Thành công: {"ok": true, "status": "created" | "duplicate" | "updated", "id": "..."}. Lỗi: {"ok": false, "error": {...}}.
    """
    note = " ".join((note or "").split())
    if not note:
        return _err("EMPTY_NOTE", "Ghi chú rỗng.")
    if len(note) > MAX_NOTE_CHARS:
        return _err("NOTE_TOO_LONG", f"Tối đa {MAX_NOTE_CHARS} ký tự.")
    try:
        notes = _read()
    except MemoryCorrupt:
        return _err("MEMORY_CORRUPT", "memory.json bị hỏng, chưa ghi gì. Hãy sửa hoặc xóa file.")
    for existing in notes:
        if _same_note(existing["text"], note):
            if _norm(note) != _norm(existing["text"]) and len(note) > len(existing["text"]):
                previous, existing["text"] = existing["text"], note
                _write(notes)
                return json.dumps({"ok": True, "status": "updated", "id": existing["id"], "previous": previous}, ensure_ascii=False)
            return json.dumps({"ok": True, "status": "duplicate", "id": existing["id"], "existing": existing["text"]}, ensure_ascii=False)
    new = {"id": uuid.uuid4().hex[:6], "text": note, "created": date.today().isoformat()}
    notes.append(new)
    _write(notes)
    return json.dumps({"ok": True, "status": "created", "id": new["id"]}, ensure_ascii=False)


@tool
def forget_memory(query: str) -> str:
    """Xóa MỘT ghi chú trong memory khi người dùng yêu cầu quên điều gì đó.

    query là id của ghi chú, hoặc cụm từ đặc trưng nằm trong ghi chú (không phân biệt hoa thường).
    Chỉ xóa khi đúng 1 ghi chú khớp; nếu nhiều ghi chú khớp, trả về candidates (id + text) để chọn lại bằng id.
    Thành công: {"ok": true, "removed": "..."}. Lỗi: {"ok": false, "error": {...}}.
    """
    q = " ".join((query or "").split()).lower()
    if len(q) < MIN_QUERY_CHARS:
        return _err("QUERY_TOO_SHORT", f"Cần ít nhất {MIN_QUERY_CHARS} ký tự.")
    try:
        notes = _read()
    except MemoryCorrupt:
        return _err("MEMORY_CORRUPT", "memory.json bị hỏng, chưa xóa gì. Hãy sửa hoặc xóa file.")
    if not notes:
        return _err("MEMORY_EMPTY", "Chưa có gì trong memory.")
    matches = [n for n in notes if n["id"] == q] or [n for n in notes if q in n["text"].lower()]
    if not matches:
        return _err("NOT_FOUND", f"Không có ghi chú nào khớp '{query}'.")
    if len(matches) > 1:
        return _err(
            "AMBIGUOUS_QUERY",
            "Nhiều ghi chú khớp, chưa xóa gì. Hãy gọi lại với id cụ thể.",
            candidates=[{"id": n["id"], "text": n["text"]} for n in matches],
        )
    target = matches[0]
    _write([n for n in notes if n["id"] != target["id"]])
    return json.dumps({"ok": True, "removed": target["text"]}, ensure_ascii=False)


def clear_memory() -> bool:
    """Xóa toàn bộ memory. Không phải tool: dùng cho UI/test, không đưa cho model."""
    f = _file()
    if f.exists():
        f.unlink()
        return True
    return False