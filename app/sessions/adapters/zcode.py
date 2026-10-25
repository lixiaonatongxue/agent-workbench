"""ZCode adapter.

Reads ~/.zcode/cli/db/db.sqlite (opened read-only; the history may live on
another drive via a junction — the standard path still works).

Schema (as observed):
  session(id, directory, title, time_created ms, time_updated, time_deleted)
  message(id, session_id, time_created ms, sequence, data JSON{role, semantics})
  part(id, message_id, session_id, sequence, data JSON{type, text | tool})
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.sessions.adapters import BaseAdapter, brief
from app.sessions.models import MessageRecord, SessionRecord

DB_REL = Path(".zcode") / "cli" / "db" / "db.sqlite"

# semantics.kind values worth indexing; reminders are injected noise
KEEP_KINDS = {"user_prompt", "assistant_response", None}


class ZcodeAdapter(BaseAdapter):
    agent_id = "zcode"
    agent_name = "ZCode"

    def sources(self) -> list[Path]:
        db = self.home / DB_REL
        return [db] if db.is_file() else []

    def parse_source(self, source: Path) -> list[SessionRecord]:
        uri = f"file:{source.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            sessions: dict[str, SessionRecord] = {}
            for row in conn.execute(
                "SELECT id, directory, title, time_created, time_updated"
                " FROM session WHERE time_deleted IS NULL"
            ):
                directory = row["directory"]
                sessions[row["id"]] = SessionRecord(
                    agent=self.agent_id,
                    external_id=row["id"],
                    project=Path(directory).name if directory else "unknown",
                    project_path=directory,
                    title=row["title"],
                    started_at=(row["time_created"] or 0) / 1000.0,
                    ended_at=(row["time_updated"] or 0) / 1000.0 or None,
                    source_path=str(source),
                )

            parts_by_msg: dict[str, list[dict]] = {}
            for row in conn.execute(
                "SELECT message_id, data FROM part"
                " ORDER BY message_id, sequence"
            ):
                try:
                    part = json.loads(row["data"])
                except (TypeError, ValueError):
                    continue
                parts_by_msg.setdefault(row["message_id"], []).append(part)

            for row in conn.execute(
                "SELECT id, session_id, time_created, data"
                " FROM message ORDER BY session_id, sequence"
            ):
                try:
                    data = json.loads(row["data"])
                except (TypeError, ValueError):
                    continue
                role = data.get("role")
                if role not in ("user", "assistant"):
                    continue
                kind = (data.get("semantics") or {}).get("kind")
                if kind not in KEEP_KINDS:
                    continue
                sess = sessions.get(row["session_id"])
                if sess is None:
                    continue
                chunks: list[str] = []
                tool_name = None
                for part in parts_by_msg.get(row["id"], []):
                    ptype = part.get("type")
                    if ptype == "text" and part.get("text"):
                        chunks.append(part["text"])
                    elif ptype == "tool":
                        name = part.get("tool") or "tool"
                        state = part.get("state") or {}
                        inp = state.get("input") or {}
                        arg = next(iter(inp.values()), "") if isinstance(inp, dict) else ""
                        chunks.append(f"[tool] {name}({brief(arg, 80)})")
                        tool_name = tool_name or name
                content = "\n".join(c for c in chunks if c.strip())
                if not content:
                    continue
                sess.messages.append(MessageRecord(
                    role=role,
                    ts=(row["time_created"] or 0) / 1000.0,
                    content=content,
                    tool_name=tool_name,
                ))

            for sess in sessions.values():
                sess.messages.sort(key=lambda m: m.ts)
                if sess.messages and not sess.started_at:
                    sess.started_at = sess.messages[0].ts
                if sess.messages:
                    sess.ended_at = sess.messages[-1].ts
            return [s for s in sessions.values() if s.messages]
        finally:
            conn.close()
