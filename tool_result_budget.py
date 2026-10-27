"""Bound oversized read_file tool responses before they enter an agent's context.

Works with LangChain AgentMiddleware. This is *lossy*: the agent must request
additional chunks when it needs a complete file, rather than treating the
excerpt as the entire source.
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

IMPORTANT = re.compile(r"\b(ERROR|WARN(?:ING)?|CRITICAL|FATAL|TRACEBACK|EXCEPTION|TIMEOUT|FAILED)\b", re.I)


def _excerpt(text: str, budget: int) -> str:
    """Return a bounded, human-readable sample of text, favoring error lines."""
    if len(text) <= budget:
        return text
    lines = text.splitlines()
    # Use line indices so chronological ordering is preserved.
    indices = list(dict.fromkeys(
        list(range(min(3, len(lines))))
        + [i for i, line in enumerate(lines) if IMPORTANT.search(line)]
        + list(range(max(0, len(lines) - 3), len(lines)))
    ))
    indices.sort()
    header = f"[TRUNCATED: {len(text)} original characters; selected lines only; request chunks for full analysis]\n"
    out = header
    previous = -1
    for i in indices:
        prefix = f"[... {i - previous - 1} omitted lines ...]\n" if i > previous + 1 else ""
        addition = prefix + f"[line {i + 1}] {lines[i]}\n"
        if len(out) + len(addition) > budget - 100:
            break
        out += addition
        previous = i
    if len(out) < budget - 100:
        out += "[Excerpt incomplete; retrieve remaining lines using a bounded read.]"
    return out[:budget]


class ToolResultBudgetMiddleware(AgentMiddleware):
    """Trim oversized successful read_file results without touching on-disk files."""

    def __init__(self, max_chars: int = 4500, tool_names: tuple[str, ...] = ("read_file",)):
        if max_chars < 500:
            raise ValueError("max_chars must be at least 500")
        self.max_chars = max_chars
        self.tool_names = set(tool_names)

    def wrap_tool_call(self, request: Any, handler: Any) -> ToolMessage:
        result = handler(request)
        if not isinstance(result, ToolMessage) or request.tool_call.get("name") not in self.tool_names:
            return result
        raw = result.content
        if not isinstance(raw, str) or len(raw) <= self.max_chars:
            return result
        args = request.tool_call.get("args") or {}
        if str(args.get("path", "")).replace("\\", "/").lstrip("./").startswith("skills/"):
            return result  # hướng dẫn skill phải vào context đầy đủ, chỉ cắt dữ liệu/log
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("content"), str):
            original = payload["content"]
            if payload.get("ok") is not True:
                return result
            # Preserve metadata and the JSON response format, but mark it as partial.
            meta = {k: v for k, v in payload.items() if k != "content"}
            meta.update({"truncated": True, "original_content_chars": len(original),
                         "notice": "Partial excerpt, not the complete file. Read smaller chunks for exhaustive analysis."})
            overhead = len(json.dumps({**meta, "content": ""}, ensure_ascii=False))
            room = self.max_chars - overhead - 40
            if room < 300:
                return result  # safer than emitting an invalid or misleading response
            meta["content"] = _excerpt(original, room)
            replacement = json.dumps(meta, ensure_ascii=False)
        else:
            replacement = _excerpt(raw, self.max_chars)
        return result.model_copy(update={"content": replacement})