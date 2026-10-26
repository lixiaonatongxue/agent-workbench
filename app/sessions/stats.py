"""Usage statistics over the session index (v0.2 pulled forward)."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone


def build_stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT agent, project, started_at, ended_at, msg_count FROM sessions"
    ).fetchall()

    totals = {
        "sessions": len(rows),
        "messages": sum(r["msg_count"] or 0 for r in rows),
        "agents": len({r["agent"] for r in rows}),
        "projects": len({r["project"] for r in rows if r["project"]}),
        "first": min((r["started_at"] for r in rows if r["started_at"]), default=None),
        "last": max((r["started_at"] for r in rows if r["started_at"]), default=None),
    }

    by_agent: dict[str, dict] = {}
    for r in rows:
        entry = by_agent.setdefault(
            r["agent"], {"agent": r["agent"], "sessions": 0, "messages": 0})
        entry["sessions"] += 1
        entry["messages"] += r["msg_count"] or 0
    for entry in by_agent.values():
        entry["avg_messages"] = round(
            entry["messages"] / entry["sessions"], 1) if entry["sessions"] else 0

    # last 12 months, per agent stacks
    now = datetime.now(timezone.utc)
    months: list[str] = []
    for delta in range(11, -1, -1):
        y, m = now.year, now.month - delta
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y:04d}-{m:02d}")
    month_idx = {key: i for i, key in enumerate(months)}
    month_sessions = [defaultdict(int) for _ in months]
    month_totals = [0] * 12
    for r in rows:
        if not r["started_at"]:
            continue
        key = datetime.fromtimestamp(r["started_at"], tz=timezone.utc).strftime("%Y-%m")
        idx = month_idx.get(key)
        if idx is None:
            continue
        month_sessions[idx][r["agent"]] += 1
        month_totals[idx] += 1

    by_month = [{
        "month": months[i],
        "sessions": month_totals[i],
        "by_agent": dict(month_sessions[i]),
    } for i in range(12)]

    project_stats: dict[str, dict] = {}
    for r in rows:
        if not r["project"]:
            continue
        entry = project_stats.setdefault(
            r["project"], {"project": r["project"], "sessions": 0, "messages": 0})
        entry["sessions"] += 1
        entry["messages"] += r["msg_count"] or 0
    top_projects = sorted(project_stats.values(),
                          key=lambda p: p["sessions"], reverse=True)[:8]

    return {
        "totals": totals,
        "by_agent": sorted(by_agent.values(), key=lambda a: a["sessions"], reverse=True),
        "by_month": by_month,
        "top_projects": top_projects,
    }
