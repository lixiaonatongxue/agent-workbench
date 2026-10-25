"""Markdown export for a single session (W3 deliverable, wired in W2)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

ROLE_ICON = {"user": "👤", "assistant": "🤖", "tool": "🔧"}


def _fmt_ts(ts: float) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime(
        "%Y-%m-%d %H:%M")


def export_session_markdown(conn: sqlite3.Connection, session_id: int) -> str | None:
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
