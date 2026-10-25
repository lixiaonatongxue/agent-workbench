"""Read-side queries for the session index (timeline, filters, FTS search)."""

from __future__ import annotations

import sqlite3

from app.sessions.indexer import fts_quote


def _session_filters(agent: str | None, project: str | None) -> tuple[str, list]:
    clauses, params = [], []
    if agent:
        clauses.append("s.agent = ?")
        params.append(agent)
    if project:
        clauses.append("s.project = ?")
        params.append(project)
    where = (" AND " + " ".join(clauses)) if clauses else ""
    return where, params


def list_sessions(
    conn: sqlite3.Connection,
    agent: str | None = None,
    project: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))

    if q:
        match = fts_quote(q)
        where, params = _session_filters(agent, project)
        total = conn.execute(
            "SELECT COUNT(DISTINCT s.id) FROM messages_fts f"
            " JOIN messages m ON m.id = f.rowid"
            " JOIN sessions s ON s.id = m.session_id"
            f" WHERE messages_fts MATCH ?{where}",
            [match] + params,
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT s.id, COUNT(m.id) AS hit_count"
            " FROM messages_fts f"
            " JOIN messages m ON m.id = f.rowid"
            " JOIN sessions s ON s.id = m.session_id"
            f" WHERE messages_fts MATCH ?{where}"
            " GROUP BY s.id ORDER BY hit_count DESC, s.started_at DESC"
            " LIMIT ? OFFSET ?",
            [match] + params + [limit, offset],
        ).fetchall()
        hit_counts = {r["id"]: r["hit_count"] for r in rows}
        # snippet() cannot run inside the aggregate above; fetch per session
        items = []
        for sid in hit_counts:
            sess = conn.execute(
                "SELECT id, agent, project, title, started_at, ended_at,"
                " msg_count, source_path FROM sessions WHERE id = ?", (sid,)
            ).fetchone()
            if sess is None:
                continue
            snip = conn.execute(
                "SELECT snippet(messages_fts, 0, '【', '】', '…', 16) AS snippet"
                " FROM messages_fts f JOIN messages m ON m.id = f.rowid"
                " WHERE messages_fts MATCH ? AND m.session_id = ? LIMIT 1",
                (match, sid),
            ).fetchone()
            item = dict(sess)
            item["hit_count"] = hit_counts[sid]
            item["snippet"] = (snip["snippet"] if snip else "") or ""
            items.append(item)
        items.sort(key=lambda it: (-it["hit_count"], -(it["started_at"] or 0)))
    else:
        where, params = _session_filters(agent, project)
        total = conn.execute(
            f"SELECT COUNT(*) FROM sessions s WHERE 1=1{where}", params).fetchone()[0]
        rows = conn.execute(
            "SELECT id, agent, project, title, started_at, ended_at, msg_count,"
            " source_path FROM sessions s WHERE 1=1"
            f"{where} ORDER BY started_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        items = [dict(r) for r in rows]

    return {"total": total, "limit": limit, "offset": offset, "items": items}


def filter_options(conn: sqlite3.Connection) -> dict:
    agents = [r["agent"] for r in conn.execute(
        "SELECT DISTINCT agent FROM sessions ORDER BY agent")]
    projects = [r["project"] for r in conn.execute(
        "SELECT DISTINCT project FROM sessions WHERE project IS NOT NULL"
        " ORDER BY project")]
    counts = {r["agent"]: r["n"] for r in conn.execute(
        "SELECT agent, COUNT(*) AS n FROM sessions GROUP BY agent")}
    return {"agents": [
        {"id": a, "count": counts.get(a, 0)} for a in agents], "projects": projects}


def session_detail(conn: sqlite3.Connection, session_id: int) -> dict | None:
    sess = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if sess is None:
        return None
    messages = conn.execute(
        "SELECT role, ts, content, tool_name FROM messages"
        " WHERE session_id = ? ORDER BY ts, id", (session_id,)).fetchall()
    out = dict(sess)
    out["messages"] = [dict(m) for m in messages]
    return out


def search_messages(
    conn: sqlite3.Connection, q: str, agent: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Message-level hits with session context (used by search view)."""
    match = fts_quote(q)
    where, params = _session_filters(agent, None)
    rows = conn.execute(
        "SELECT m.id, m.role, m.ts, m.content, m.session_id,"
        " s.agent, s.project, s.title,"
        " snippet(messages_fts, 0, '【', '】', '…', 20) AS snippet"
        " FROM messages_fts f"
        " JOIN messages m ON m.id = f.rowid"
        " JOIN sessions s ON s.id = m.session_id"
        f" WHERE messages_fts MATCH ?{where}"
        " ORDER BY m.ts DESC LIMIT ?",
        [match] + params + [max(1, min(int(limit or 50), 200))],
    ).fetchall()
    return [dict(r) for r in rows]
