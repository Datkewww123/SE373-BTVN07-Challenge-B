"""File tools: read_file và write_file trong workspace của project.

Path luôn tương đối workspace. Path được resolve (kể cả symlink) rồi kiểm tra vẫn nằm trong
workspace (đọc) hoặc workspace/output (ghi). Lỗi dự kiến trả về JSON {"ok": false, "error": {...}}
để quay lại model như tool result.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool
import re

import paths

MAX_READ_BYTES = 200_000


def _error(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message}}


def _resolve(workspace: Path, path: str) -> tuple[Path | None, dict | None]:
    raw = (path or "").strip()
    if not raw:
        return None, _error("INVALID_PATH", "Path rỗng. Dùng đường dẫn tương đối workspace, ví dụ data/weekly_notes.md.")
    if Path(raw).is_absolute() or raw.startswith("~"):
        return None, _error("PATH_OUTSIDE_WORKSPACE", f"Không chấp nhận đường dẫn tuyệt đối: {raw}. Dùng đường dẫn tương đối workspace.")
    root = workspace.resolve()
    target = (root / raw).resolve()
    if not target.is_relative_to(root):
        return None, _error("PATH_OUTSIDE_WORKSPACE", f"Đường dẫn thoát ra ngoài workspace: {raw}")
    return target, None


def _read(workspace: Path, path: str) -> dict:
    target, error = _resolve(workspace, path)
    if error:
        return error
    rel = target.relative_to(workspace.resolve()).as_posix()
    if not target.exists():
        return _error("FILE_NOT_FOUND", f"Không tìm thấy file: {rel}")
    if target.is_dir():
        return _error("IS_A_DIRECTORY", f"Đây là thư mục, không phải file: {rel}")
    size = target.stat().st_size
    if size > MAX_READ_BYTES:
        return _error("FILE_TOO_LARGE", f"File {rel} có {size} bytes, vượt giới hạn {MAX_READ_BYTES} bytes. Không đọc một phần.")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _error("NOT_UTF8_TEXT", f"File {rel} không phải văn bản UTF-8.")
    return {"ok": True, "path": rel, "content": content}

def _list(workspace: Path, path: str) -> dict:
    target, error = _resolve(workspace, path)
    if error:
        return error

    rel = target.relative_to(workspace.resolve()).as_posix()

    if not target.exists():
        return _error("DIRECTORY_NOT_FOUND", f"Không tìm thấy thư mục: {rel}")

    if not target.is_dir():
        return _error("NOT_A_DIRECTORY", f"Đây là file, không phải thư mục: {rel}")

    try:
        items = []

        for item in target.iterdir():
            item_type = "directory" if item.is_dir() else "file"

            item_rel = item.relative_to(workspace.resolve()).as_posix()

            items.append({
                "name": item.name,
                "path": item_rel,
                "type": item_type,
            })

        items.sort(key=lambda x: x["name"])

        return {
            "ok": True,
            "path": rel,
            "items": items,
        }

    except OSError as e:
        return _error("LIST_FAILED", f"Không thể liệt kê thư mục {rel}: {e}")

def _write(workspace: Path, path: str, content: str) -> dict:
    target, error = _resolve(workspace, path)
    if error:
        return error
    output_root = (workspace / paths.OUTPUT_SUBDIR).resolve()
    if not target.is_relative_to(output_root) or target == output_root:
        return _error("PATH_OUTSIDE_OUTPUT", f"Chỉ được ghi file dưới {paths.OUTPUT_SUBDIR}/ (ví dụ output/summary.md). Path nhận được: {path}")
    rel = target.relative_to(workspace.resolve()).as_posix()
    if target.is_dir():
        return _error("IS_A_DIRECTORY", f"Đây là thư mục, không ghi đè được: {rel}")
    status = "updated" if target.exists() else "created"
    target.parent.mkdir(parents=True, exist_ok=True)
    # mkdir có thể đi qua symlink tạo sau lần resolve đầu; kiểm tra lại trước khi ghi
    if not target.parent.resolve().is_relative_to(output_root):
        return _error("PATH_OUTSIDE_OUTPUT", f"Thư mục đích thoát khỏi {paths.OUTPUT_SUBDIR}/: {path}")
    data = content.encode("utf-8")
    target.write_bytes(data)
    return {"ok": True, "path": rel, "bytes": len(data), "status": status}


@tool
def read_file(path: str) -> str:
    """Đọc một file văn bản UTF-8 trong workspace và trả về JSON.

    path là đường dẫn tương đối workspace, ví dụ: data/weekly_notes.md, output/summary.md.
    Dùng để đọc dữ liệu đầu vào, file SKILL.md của một skill và các file reference trong thư mục skill.
    Thành công: {"ok": true, "path": ..., "content": ...}. Lỗi: {"ok": false, "error": {"code": ..., "message": ...}}.
    """
    return json.dumps(_read(paths.WORKSPACE_DIR, path), ensure_ascii=False)

@tool
def list_files(path: str) -> str:
    """Liệt kê trực tiếp các file và thư mục trong workspace và trả về JSON.

    Không duyệt đệ quy.

    path là đường dẫn tương đối workspace, ví dụ:
    . hoặc data hoặc data/policies.

    Thành công:
    {
        "ok": true,
        "path": "...",
        "items": [
            {
                "name": "...",
                "path": "...",
                "type": "file" | "directory"
            }
        ]
    }

    Lỗi:
    {
        "ok": false,
        "error": {
            "code": "...",
            "message": "..."
        }
    }
    """
    return json.dumps(
        _list(paths.WORKSPACE_DIR, path),
        ensure_ascii=False
    )

@tool
def write_file(path: str, content: str) -> str:
    """Ghi nội dung văn bản UTF-8 vào một file dưới output/ của workspace và trả về JSON.

    path là đường dẫn tương đối workspace và phải bắt đầu bằng output/, ví dụ output/summary.md.
    Tự tạo thư mục con. Ghi đè nếu file đã tồn tại.
    Thành công: {"ok": true, "path": ..., "bytes": ..., "status": "created" | "updated"}. Lỗi: {"ok": false, "error": {...}}.
    """
    return json.dumps(_write(paths.WORKSPACE_DIR, path, content), ensure_ascii=False)

MAX_LOG_LINES = 50
_TIME_RE = re.compile(r"\b(\d{2}:\d{2}:\d{2})\b")


def _norm_time(value: str, *, end: bool) -> str | None:
    """'13:39' -> '13:39:00' (start) hoặc '13:39:59' (end); trả None nếu không phải giờ hợp lệ."""
    parts = (value or "").strip().split(":")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() and 1 <= len(p) <= 2 for p in parts):
        return None
    h, m, sec = (int(parts[i]) if i < len(parts) else (59 if end else 0) for i in range(3))
    if h > 23 or m > 59 or sec > 59:
        return None
    return f"{h:02d}:{m:02d}:{sec:02d}"


@tool
def read_log_time_range(
    path: str,
    start_time: str,
    end_time: str,
) -> str:
    """Đọc các dòng log trong khoảng giờ HH:MM:SS (hoặc HH:MM) trong một ngày, ví dụ start_time=13:39, end_time=13:41.

    Trả tối đa 50 dòng đầu khớp. Nếu còn nhiều hơn, cuối kết quả có dòng [TRUNCATED ...] cho biết giờ để đọc tiếp.
    """
    file_path = (paths.WORKSPACE_DIR / path).resolve()
    workspace = paths.WORKSPACE_DIR.resolve()

    if not file_path.is_relative_to(workspace):
        return "Lỗi: Đường dẫn nằm ngoài workspace."

    if not file_path.is_file():
        return f"Không tìm thấy file: {path}"

    start = _norm_time(start_time, end=False)
    end = _norm_time(end_time, end=True)
    if start is None or end is None:
        return f"Lỗi: start_time/end_time phải dạng HH:MM hoặc HH:MM:SS (nhận được {start_time!r}, {end_time!r})."

    results = []

    with file_path.open(encoding="utf-8") as f:
        for line in f:
            match = _TIME_RE.search(line)

            if match and start <= match.group(1) <= end:
                results.append(line.rstrip())

    if not results:
        return "Không tìm thấy log trong khoảng thời gian yêu cầu."

    shown = results[:MAX_LOG_LINES]
    if len(results) > MAX_LOG_LINES:
        last = _TIME_RE.search(shown[-1]).group(1)
        shown.append(
            f"[TRUNCATED: hiển thị {MAX_LOG_LINES}/{len(results)} dòng khớp, đến {last}; "
            f"gọi lại với start_time sau {last} để đọc phần còn lại]"
        )
    return "\n".join(shown)