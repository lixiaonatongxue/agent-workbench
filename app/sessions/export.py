"""Markdown export for a single session, with optional secret masking."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

ROLE_ICON = {"user": "👤", "assistant": "🤖", "tool": "🔧"}

SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{16,}"), "sk-***MASKED***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "gh*_***MASKED***"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}"), "AKIA***MASKED***"),
    (re.compile(r"\bxox[apsb]-[A-Za-z0-9-]{10,}"), "xox*-***MASKED***"),
    (re.compile(r"(?i)\b(api[_-]?key|apikey|token|password|passwd|secret)"
                r"(\s*[=:]\s*)(['\"]?)[A-Za-z0-9_\-./+]{8,}\3"),
     r"\1\2***MASKED***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-./+]{16,}"), "bearer ***MASKED***"),
]


def mask_secrets(text: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _fmt_ts(ts: float) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime(
        "%Y-%m-%d %H:%M")


def export_session_markdown(conn: sqlite3.Connection, session_id: int,
                            mask: bool = False) -> str | None:
    sess = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if sess is None:
        return None
    messages = conn.execute(
        "SELECT role, ts, content, tool_name FROM messages"
        " WHERE session_id = ? ORDER BY ts, id", (session_id,)).fetchall()

    lines: list[str] = []
    title = sess["title"] or f"{sess['agent']} session"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- **Agent**: {sess['agent']}")
    if sess["project"]:
        lines.append(f"- **项目**: {sess['project']}"
                     + (f"（{sess['project_path']}）" if sess["project_path"] else ""))
    lines.append(f"- **开始**: {_fmt_ts(sess['started_at'] or 0)}")
    if sess["ended_at"]:
        lines.append(f"- **结束**: {_fmt_ts(sess['ended_at'])}")
    lines.append(f"- **消息数**: {sess['msg_count']}")
    lines.append(f"- **来源**: `{sess['source_path']}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    for m in messages:
        icon = ROLE_ICON.get(m["role"], "·")
        role_label = m["role"] or "message"
        stamp = _fmt_ts(m["ts"] or 0)
        lines.append(f"## {icon} {role_label} · {stamp}")
        lines.append("")
        content = m["content"] or ""
        if mask:
            content = mask_secrets(content)
        tool_lines = [ln for ln in content.splitlines() if ln.startswith("[tool")]
        text_lines = [ln for ln in content.splitlines() if not ln.startswith("[tool")]
        if text_lines:
            lines.append("\n".join(text_lines).strip())
            lines.append("")
        if tool_lines:
            lines.append("```")
            lines.extend(tool_lines)
            lines.append("```")
            lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Exported by Agent Workbench · 100% local*")
    return "\n".join(lines)
