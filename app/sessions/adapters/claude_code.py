"""Claude Code adapter.

Reads ~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl — one JSON object
per line. Each line carries type (user/assistant/summary/...), the message
body, an ISO timestamp and the working directory. Sidechain (subagent) lines
are skipped to keep the main conversation timeline readable.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.sessions.adapters import BaseAdapter, brief
from app.sessions.models import MessageRecord, SessionRecord

PROJECTS_REL = Path(".claude") / "projects"


def _parse_ts(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _content_text(content) -> tuple[str, str | None]:
    """Extract display text + optional tool name from a claude message body."""
    if isinstance(content, str):
        return content, None
    if not isinstance(content, list):
        return "", None
    chunks: list[str] = []
    tool_name = None
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text" and block.get("text"):
            chunks.append(block["text"])
        elif btype == "tool_use":
            name = block.get("name") or "tool"
            arg = ""
            inp = block.get("input")
            if isinstance(inp, dict):
                arg = next(iter(inp.values()), "")
            chunks.append(f"[tool] {name}({brief(arg, 80)})")
            tool_name = tool_name or name
        elif btype == "tool_result":
            body = block.get("content")
            if isinstance(body, list):
                body = " ".join(
                    p.get("text", "") for p in body if isinstance(p, dict))
            chunks.append(f"[tool_result] {brief(body or '', 80)}")
        # "thinking" and unknown block types are skipped
    return "\n".join(c for c in chunks if c.strip()), tool_name


class ClaudeCodeAdapter(BaseAdapter):
    agent_id = "claude-code"
    agent_name = "Claude Code"

    def sources(self) -> list[Path]:
        projects = self.home / PROJECTS_REL
        if not projects.is_dir():
            return []
        return sorted(p for p in projects.rglob("*.jsonl") if p.is_file())

    def parse_source(self, source: Path) -> list[SessionRecord]:
        session_id = source.stem
        messages: list[MessageRecord] = []
        project_path: str | None = None
        started = 0.0
        ended = 0.0

        try:
            with open(source, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("isSidechain"):
                        continue
                    etype = entry.get("type")
                    if etype not in ("user", "assistant"):
                        continue
                    msg = entry.get("message") or {}
                    content, tool_name = _content_text(msg.get("content"))
                    if not content:
                        continue
                    ts = _parse_ts(entry.get("timestamp"))
                    if ts:
                        started = started or ts
                        ended = max(ended, ts)
                    cwd = entry.get("cwd")
                    if cwd and not project_path:
                        project_path = cwd
                    messages.append(MessageRecord(
                        role=etype, ts=ts, content=content, tool_name=tool_name))
        except OSError:
            return []

        if not messages:
            return []
        first_user = next((m for m in messages if m.role == "user"), None)
        title = None
        if first_user:
            title = brief(first_user.content, 80)
        return [SessionRecord(
            agent=self.agent_id,
            external_id=session_id,
            project=Path(project_path).name if project_path else (source.parent.name),
            project_path=project_path,
            title=title,
            started_at=started,
            ended_at=ended or None,
            source_path=str(source),
            messages=messages,
        )]
