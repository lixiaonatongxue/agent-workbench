"""Build the Rules Doctor report from the local scan index.

Everything here is derived, read-only computation over what db.save_scan
stored: per-agent/per-repo token sums, near-duplicate block groups, staleness
flags, and a cost estimate parameterized by user settings.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone

from app.db import get_settings
from app.doctor.contradictions import detect_contradictions
from app.doctor.simhash import group_near_duplicates
from app.scan.rulefiles import RuleScanner

MAX_DUPLICATE_GROUPS = 200


def _iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _agent_names() -> dict[str, str]:
    scanner = RuleScanner()
    return {a["id"]: scanner.agent_name(a["id"]) for a in scanner.agents}


def build_report(conn: sqlite3.Connection) -> dict:
    settings = get_settings(conn)
    now = time.time()
    names = _agent_names()

    files = [dict(row) for row in conn.execute(
        "SELECT * FROM rule_files ORDER BY tokens_est DESC")]
    repos = {row["path"]: dict(row) for row in conn.execute("SELECT * FROM repos")}
    last_run = conn.execute(
        "SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()

    # ---------- totals & per-agent / per-repo aggregation ----------
    totals = {"files": len(files), "tokens": 0, "lines": 0, "chars": 0, "cjk_chars": 0}
    agent_tokens: dict[str, dict] = {}
    repo_tokens: dict[str, dict] = {}

    for f in files:
        if f.get("error"):
            continue
        totals["tokens"] += f["tokens_est"] or 0
        totals["lines"] += f["lines"] or 0
        totals["chars"] += f["chars"] or 0
        totals["cjk_chars"] += f["cjk_chars"] or 0
        for agent in json.loads(f["agents"]):
            entry = agent_tokens.setdefault(agent, {"global": 0, "repos": {}})
            if f["repo"] is None:
                entry["global"] += f["tokens_est"] or 0
            else:
                entry["repos"][f["repo"]] = (entry["repos"].get(f["repo"], 0)
                                             + (f["tokens_est"] or 0))
        if f["repo"] is not None:
            rr = repo_tokens.setdefault(f["repo"], {})
            rr_json = json.loads(f["agents"])
            for agent in rr_json:
                rr[agent] = rr.get(agent, 0) + (f["tokens_est"] or 0)

    per_agent = []
    for agent, entry in sorted(agent_tokens.items()):
        best_repo, best_tokens = None, 0
        for repo, tokens in entry["repos"].items():
            if tokens > best_tokens:
                best_repo, best_tokens = repo, tokens
        per_agent.append({
            "id": agent,
            "name": names.get(agent, agent),
            "global_tokens": entry["global"],
            "repo_count": len(entry["repos"]),
            "max_repo_tokens": best_tokens,
            "max_repo": best_repo,
            "max_session_injection": entry["global"] + best_tokens,
        })
    per_agent.sort(key=lambda a: a["max_session_injection"], reverse=True)

    per_repo = []
    for repo, tokens_by_agent in sorted(repo_tokens.items(),
                                        key=lambda kv: sum(kv[1].values()), reverse=True):
        info = repos.get(repo, {})
        per_repo.append({
            "repo": repo,
            "name": info.get("name"),
            "last_activity": _iso(info.get("last_activity")),
            "tokens_by_agent": {names.get(a, a): t for a, t in tokens_by_agent.items()},
            "total_tokens": sum(tokens_by_agent.values()),
        })

    # ---------- duplicates (A3) ----------
    blocks = [dict(row) for row in conn.execute(
        "SELECT b.id, b.file_id, b.start_line, b.end_line, b.tokens_est, b.simhash,"
        " b.text, f.path, f.repo, f.agents"
        " FROM rule_blocks b JOIN rule_files f ON f.id = b.file_id")]
    groups = group_near_duplicates(
        [b["simhash"] & 0xFFFFFFFFFFFFFFFF for b in blocks]) if blocks else []
    duplicate_groups = []
    total_wasted = 0
    cross_file_wasted = 0
    for members_idx in groups:
        members = [blocks[i] for i in members_idx]
        wasted = sum(m["tokens_est"] or 0 for m in members) - max(
            m["tokens_est"] or 0 for m in members)
        total_wasted += wasted
        paths = {m["path"] for m in members}
        if len(paths) > 1:
            cross_file_wasted += wasted
        duplicate_groups.append({
            "cross_file": len(paths) > 1,
            "wasted_tokens": wasted,
            "members": [{
                "path": m["path"],
                "repo": m["repo"],
                "start_line": m["start_line"],
                "end_line": m["end_line"],
                "tokens_est": m["tokens_est"],
                "preview": " ".join((m["text"] or "").split())[:110],
            } for m in members],
        })
    duplicate_groups.sort(key=lambda g: g["wasted_tokens"], reverse=True)

    # ---------- contradictions (A5, heuristic) ----------
    contradictions = detect_contradictions(blocks)

    # ---------- staleness (A4) ----------
    stale_days = float(settings["stale_days"])
    active_days = float(settings["repo_active_days"])
    stale_files = []
    stale_paths = set()
    for f in files:
        if not f["mtime"] or f.get("error"):
            continue
        age_days = (now - f["mtime"]) / 86400.0
        if age_days <= stale_days:
            continue
        repo = repos.get(f["repo"]) if f["repo"] else None
        if repo is not None and repo.get("last_activity") is not None:
            repo_age = (now - repo["last_activity"]) / 86400.0
            if repo_age > active_days:
                continue  # repo itself is dormant; old rules there are expected
        stale_paths.add(f["path"])
        stale_files.append({
            "path": f["path"],
            "repo": f["repo"],
            "age_days": round(age_days),
            "mtime": _iso(f["mtime"]),
            "repo_last_activity": _iso(repo.get("last_activity")) if repo else None,
        })
    stale_files.sort(key=lambda s: s["age_days"], reverse=True)

    # ---------- cost estimate (A2) ----------
    spd = float(settings["sessions_per_day"])
    price = float(settings["price_per_mtok"])

    def year_cost(tokens: float) -> float:
        return round(tokens * spd * 365 * price / 1_000_000, 2)

    worst = per_agent[0] if per_agent else None

    files_out = [{
        "path": f["path"],
        "repo": f["repo"],
        "repo_name": repos[f["repo"]]["name"] if f["repo"] in repos else None,
        "agents": [names.get(a, a) for a in json.loads(f["agents"])],
        "lines": f["lines"],
        "chars": f["chars"],
        "tokens_est": f["tokens_est"],
        "mtime": _iso(f["mtime"]),
        "stale": f["path"] in stale_paths,
        "error": f["error"],
    } for f in files]

    return {
        "generated_at": _iso(now),
        "last_scan": dict(last_run) if last_run else None,
        "settings_snapshot": {
            "sessions_per_day": spd,
            "price_per_mtok": price,
            "currency": settings["currency"],
            "stale_days": stale_days,
            "repo_active_days": active_days,
            "cjk_ratio": settings["cjk_ratio"],
            "other_ratio": settings["other_ratio"],
        },
        "totals": totals,
        "repos_scanned": len(repos),
        "per_agent": per_agent,
        "per_repo": per_repo,
        "duplicates": {
            "groups": duplicate_groups[:MAX_DUPLICATE_GROUPS],
            "group_count": len(duplicate_groups),
            "wasted_tokens": total_wasted,
            "cross_file_wasted_tokens": cross_file_wasted,
        },
        "contradictions": contradictions,
        "stale_files": stale_files,
        "cost": {
            "worst_agent": worst["name"] if worst else None,
            "worst_session_tokens": worst["max_session_injection"] if worst else 0,
            "worst_year_cost": year_cost(worst["max_session_injection"]) if worst else 0,
            "duplicate_year_cost": year_cost(total_wasted),
            "currency": settings["currency"],
            "sessions_per_day": spd,
            "price_per_mtok": price,
        },
        "files": files_out,
    }
