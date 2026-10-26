"""Codex adapter.

Reads ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl — one JSON object per line
with {type, timestamp, payload}. Sessions are rebuilt from `response_item`
entries (payload.type == "message" with input_text/output_text blocks).
Synthetic user turns wrapped in <...> (permissions/environment/turn context)
are skipped; developer-role messages are skipped.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from app.sessions.adapters import BaseAdapter, brief
from app.sessions.models import MessageRecord, SessionRecord

SESSIONS_REL = Path(".codex") / "sessions"
_UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.(jsonl)?$", re.I)


def _parse_ts(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _content_text(content) -> str:
    """Flatten a codex content list ([{type: input_text|output_text, text}])."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks = []
    for block in content:
        if isinstance(block, dict) and block.get("text"):
            chunks.append(str(block["text"]))
    return "\n".join(chunks)


class CodexAdapter(BaseAdapter):
    agent_id = "codex"
    agent_name = "Codex"

    def sources(self) -> list[Path]:
        root = self.home / SESSIONS_REL
        if not root.is_dir():
            return []
        return sorted(p for p in root.rglob("*.jsonl") if p.stat().st_size > 0)

    def parse_source(self, source: Path) -> list[SessionRecord]:
        match = _UUID_RE.search(source.stem + ".jsonl")
        external_id = match.group(1) if match else source.stem

        messages: list[MessageRecord] = []
        project_path: str | None = None
        started, ended = 0.0, 0.0

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
                    ts = _parse_ts(entry.get("timestamp"))
                    payload = entry.get("payload")
                    if not isinstance(payload, dict):
                        continue

                    if entry.get("type") == "session_meta" and not project_path:
                        project_path = payload.get("cwd") or payload.get("originator")

                    ptype = payload.get("type")
                    if ptype == "message":
                        role = payload.get("role")
                        if role not in ("user", "assistant"):
                            continue  # developer/system context
                        text = _content_text(payload.get("content"))
                        if not text.strip():
                            continue
                        if role == "user" and text.lstrip().startswith("<"):
                            continue  # injected <environment_context> etc.
                        if ts:
                            started = started or ts
                            ended = max(ended, ts)
                        messages.append(MessageRecord(role=role, ts=ts, content=text))
                    elif ptype == "function_call":
                        name = payload.get("name") or "tool"
                        arg = payload.get("arguments") or ""
                        messages.append(MessageRecord(
                            role="tool", ts=ts,
                            content=f"[tool] {name}({brief(arg, 80)})",
                            tool_name=name))
        except OSError:
            return []

        chat = [m for m in messages if m.role in ("user", "assistant")]
        if not chat:
            return []
        started = started or (chat[0].ts or 0.0)
        first_user = next((m for m in chat if m.role == "user"), None)
        return [SessionRecord(
            agent=self.agent_id,
            external_id=external_id,
            project=Path(project_path).name if project_path else source.parent.name,
            project_path=project_path,
            title=brief(first_user.content, 80) if first_user else None,
            started_at=started,
            ended_at=ended or None,
            source_path=str(source),
            messages=messages,
        )]
