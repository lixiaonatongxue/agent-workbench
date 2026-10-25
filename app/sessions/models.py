"""Normalized session/message model shared by all adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MessageRecord:
    role: str                 # "user" | "assistant" | "tool"
    ts: float                 # unix seconds
    content: str
    tool_name: str | None = None


@dataclass
class SessionRecord:
    agent: str                # adapter agent_id, e.g. "zcode"
    external_id: str          # agent-native session id
    project: str              # display name, e.g. "sticker-manager"
    project_path: str | None  # workspace dir if known
    title: str | None
    started_at: float
    ended_at: float | None
    source_path: str
    messages: list[MessageRecord] = field(default_factory=list)

    @property
    def msg_count(self) -> int:
        return len(self.messages)
