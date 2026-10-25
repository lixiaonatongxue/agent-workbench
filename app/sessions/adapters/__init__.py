"""Adapters for each agent's local session storage.

Contract: an adapter lists its source files (db files / jsonl files), then
parses each source into SessionRecords. Parsing must be read-only, tolerant of
unknown fields, and skip broken entries instead of raising.
"""

from __future__ import annotations

from pathlib import Path

from app.sessions.models import SessionRecord


class BaseAdapter:
    agent_id: str = "base"
    agent_name: str = "Base"

    def __init__(self, user_home: str | Path | None = None):
        self.home = Path(user_home) if user_home else Path.home()

    def sources(self) -> list[Path]:
        raise NotImplementedError

    def parse_source(self, source: Path) -> list[SessionRecord]:
        raise NotImplementedError


def brief(text: str, limit: int = 100) -> str:
    one = " ".join(str(text).split())
    return one[:limit] + ("…" if len(one) > limit else "")
