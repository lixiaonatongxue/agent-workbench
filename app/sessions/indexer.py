"""Incremental indexer: adapter sources -> sessions/messages + FTS5.

Incrementality is per source file: when a source's mtime is unchanged since
the last run it is skipped; when it changed, all sessions it currently yields
replace whatever was previously indexed from that source (sessions that
disappeared from the source are dropped).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.sessions.adapters import BaseAdapter
from app.sessions.adapters.claude_code import ClaudeCodeAdapter
from app.sessions.adapters.codex import CodexAdapter
from app.sessions.adapters.zcode import ZcodeAdapter
from app.sessions.models import SessionRecord

ProgressFn = Callable[[str, int, int, str], None]


def default_adapters(user_home: str | None = None) -> list[BaseAdapter]:
    return [ZcodeAdapter(user_home), ClaudeCodeAdapter(user_home),
            CodexAdapter(user_home)]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _replace_session(conn: sqlite3.Connection, sess: SessionRecord) -> None:
    """Insert or refresh one session; message content stays in sync with FTS."""
    old = conn.execute(
        "SELECT id FROM sessions WHERE agent = ? AND external_id = ?",
        (sess.agent, sess.external_id),
    ).fetchone()
    if old is not None:
        old_id = old["id"] if not isinstance(old, tuple) else old[0]
        for row in conn.execute(
            "SELECT id, content FROM messages WHERE session_id = ?", (old_id,)
        ).fetchall():
            conn.execute(
                "INSERT INTO messages_fts(messages_fts, rowid, content)"
                " VALUES ('delete', ?, ?)", (row["id"], row["content"]))
        conn.execute("DELETE FROM messages WHERE session_id = ?", (old_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (old_id,))

    cur = conn.execute(
        "INSERT INTO sessions(agent, external_id, project, project_path, title,"
        " started_at, ended_at, msg_count, source_path)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sess.agent, sess.external_id, sess.project, sess.project_path, sess.title,
         sess.started_at, sess.ended_at, sess.msg_count, sess.source_path),
    )
    session_id = cur.lastrowid
    for m in sess.messages:
        mcur = conn.execute(
            "INSERT INTO messages(session_id, role, ts, content, tool_name)"
            " VALUES (?, ?, ?, ?, ?)",
            (session_id, m.role, m.ts, m.content, m.tool_name),
        )
        if m.content:
            conn.execute(
                "INSERT INTO messages_fts(rowid, content) VALUES (?, ?)",
                (mcur.lastrowid, m.content))


def _drop_stale_sources(conn: sqlite3.Connection, live_sources: set[str]) -> int:
    """Remove sessions whose source file no longer exists."""
    removed = 0
    rows = conn.execute("SELECT DISTINCT source_path FROM sessions").fetchall()
    for row in rows:
        src = row["source_path"]
        if src not in live_sources:
            for srow in conn.execute(
                "SELECT id FROM sessions WHERE source_path = ?", (src,)
            ).fetchall():
                sid = srow["id"]
                for mrow in conn.execute(
                    "SELECT id, content FROM messages WHERE session_id = ?", (sid,)
                ).fetchall():
                    conn.execute(
                        "INSERT INTO messages_fts(messages_fts, rowid, content)"
                        " VALUES ('delete', ?, ?)", (mrow["id"], mrow["content"]))
                conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
                conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
                removed += 1
            conn.execute("DELETE FROM index_state WHERE source_path = ?", (src,))
    return removed


def fts_quote(query: str) -> str:
    """Wrap a raw user query as a single FTS5 phrase (safe for MATCH)."""
    return '"' + query.replace('"', '""') + '"'


def index_sessions(
    conn: sqlite3.Connection,
    adapters: list[BaseAdapter] | None = None,
    force: bool = False,
    progress: ProgressFn | None = None,
) -> dict:
    stats = {"sources_seen": 0, "sources_indexed": 0, "sessions": 0,
             "messages": 0, "removed_sessions": 0, "errors": []}
    adapters = adapters if adapters is not None else default_adapters()
    all_sources: list[tuple[BaseAdapter, Path]] = []
    for adapter in adapters:
        try:
            all_sources.extend((adapter, src) for src in adapter.sources())
        except OSError as exc:
            stats["errors"].append(f"{adapter.agent_id}: {exc}")

    total = len(all_sources)
    for i, (adapter, source) in enumerate(all_sources):
        stats["sources_seen"] += 1
        if progress:
            progress("sessions", i, total, f"{adapter.agent_name}: {source.name}")
        try:
            mtime = source.stat().st_mtime
        except OSError:
            continue
        state = conn.execute(
            "SELECT source_mtime FROM index_state WHERE source_path = ?",
            (str(source),),
        ).fetchone()
        if not force and state is not None and state["source_mtime"] == mtime:
            continue

        try:
            records = adapter.parse_source(source)
        except Exception as exc:  # noqa: BLE001 — one bad source must not stop the rest
            stats["errors"].append(f"{source}: {type(exc).__name__}: {exc}")
            continue

        with conn:
            # sessions no longer present in this source disappear
            keep = {r.external_id for r in records}
            for row in conn.execute(
                "SELECT id, external_id FROM sessions WHERE source_path = ?",
                (str(source),),
            ).fetchall():
                if row["external_id"] not in keep:
                    sid = row["id"]
                    for mrow in conn.execute(
                        "SELECT id, content FROM messages WHERE session_id = ?",
                        (sid,),
                    ).fetchall():
                        conn.execute(
                            "INSERT INTO messages_fts(messages_fts, rowid, content)"
                            " VALUES ('delete', ?, ?)", (mrow["id"], mrow["content"]))
                    conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
                    conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))

            for record in records:
                _replace_session(conn, record)
                stats["messages"] += record.msg_count
            conn.execute(
                "INSERT INTO index_state(source_path, source_mtime, session_count, indexed_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(source_path) DO UPDATE SET source_mtime = excluded.source_mtime,"
                " session_count = excluded.session_count, indexed_at = excluded.indexed_at",
                (str(source), mtime, len(records), _utcnow_iso()),
            )
        stats["sources_indexed"] += 1
        stats["sessions"] += len(records)

    stats["removed_sessions"] = _drop_stale_sources(
        conn, {str(src) for _, src in all_sources})
    with conn:
        conn.commit()
    if progress:
        progress("sessions", total, total, "done")
    return stats
