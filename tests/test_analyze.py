"""Report builder tests on synthetic repos/files only."""

import os
import time

from app.doctor.analyze import build_report
from app.db import connect, save_scan, set_settings
from app.scan.rulefiles import RuleScanner

RULE_BLOCK_A = (
    "Always use pnpm as the package manager. Never run npm install directly. "
    "Run tests with pnpm test before committing any changes to the repository. "
    "Keep functions small and prefer composition over inheritance in all modules."
)
RULE_BLOCK_A_RENAMED = RULE_BLOCK_A.replace("pnpm", "yarn")
RULE_BLOCK_B = (
    "Documentation is generated with mkdocs and published on every tagged "
    "release. Contributors should preview changes locally before pushing them "
    "to the main branch of the upstream project repository."
)


def make_repo(base, name):
    repo = base / name
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    return repo


def seed(tmp_path):
    """Two repos sharing a near-duplicate rule; one stale file; one global file."""
    r1 = make_repo(tmp_path, "alpha")
    (r1 / "CLAUDE.md").write_text(f"# Rules\n\n{RULE_BLOCK_A}\n")
    r2 = make_repo(tmp_path / "group", "beta")
    (r2 / "AGENTS.md").write_text(f"# Rules\n\n{RULE_BLOCK_A_RENAMED}\n\n{RULE_BLOCK_B}\n")
    r3 = make_repo(tmp_path / "group", "dormant")
    stale_file = r3 / "CLAUDE.md"
    stale_file.write_text(f"# Old rules\n\n{RULE_BLOCK_B}\n")
    old = time.time() - 200 * 86400
    os.utime(stale_file, (old, old))

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text(f"# Global\n\n{RULE_BLOCK_B}\n")

    scanner = RuleScanner()
    files, repos = scanner.scan([str(tmp_path)], include_global=True, user_home=str(home))
    conn = connect(tmp_path / "t.sqlite3")
    save_scan(conn, files, repos, [str(tmp_path)])
    return conn, r3


def test_totals_and_files(tmp_path):
    conn, _ = seed(tmp_path)
    report = build_report(conn)
    assert report["totals"]["files"] == 4
    assert report["repos_scanned"] == 3
    paths = [f["path"] for f in report["files"]]
    assert any(p.endswith("AGENTS.md") for p in paths)
    ag = next(f for f in report["files"] if p_end(f["path"], "AGENTS.md"))
    assert set(ag["agents"]) == {"Codex", "ZCode"}
    conn.close()


def p_end(path, suffix):
    return path.replace("\\", "/").endswith(suffix)


def test_duplicate_detection_cross_file(tmp_path):
    conn, _ = seed(tmp_path)
    report = build_report(conn)
    dup = report["duplicates"]
    assert dup["group_count"] >= 1
    cross = [g for g in dup["groups"] if g["cross_file"]]
    assert cross, "near-duplicate block copied across repos should group"
    top = cross[0]
    assert top["wasted_tokens"] > 0
    member_paths = {m["path"] for m in top["members"]}
    assert len(member_paths) >= 2
    assert dup["cross_file_wasted_tokens"] > 0
    conn.close()


def test_staleness_flags_old_file_in_active_repo_only(tmp_path):
    conn, dormant_repo = seed(tmp_path)
    report = build_report(conn)
    stale_paths = [s["path"] for s in report["stale_files"]]
    assert len(stale_paths) == 1
    assert "dormant" in stale_paths[0].replace("\\", "/")

    # make the repo dormant too -> the stale flag disappears
    conn.execute("UPDATE repos SET last_activity = ? WHERE path = ?",
                 (time.time() - 90 * 86400, str(dormant_repo)))
    conn.commit()
    report = build_report(conn)
    assert report["stale_files"] == []
    conn.close()


def test_per_agent_and_cost(tmp_path):
    conn, _ = seed(tmp_path)
    report = build_report(conn)
    by_name = {a["name"]: a for a in report["per_agent"]}
    assert by_name["Claude Code"]["global_tokens"] > 0
    # worst injection = global + biggest repo, cost = tokens*spd*365*price/1e6
    worst = report["per_agent"][0]
    expected = round(worst["max_session_injection"] * 10 * 365 * 15.0 / 1e6, 2)
    assert report["cost"]["worst_year_cost"] == expected
    assert report["cost"]["worst_agent"] == worst["name"]

    set_settings(conn, {"sessions_per_day": 4, "price_per_mtok": 3.0})
    report = build_report(conn)
    w = report["per_agent"][0]
    assert report["cost"]["worst_year_cost"] == round(
        w["max_session_injection"] * 4 * 365 * 3.0 / 1e6, 2)
    conn.close()


def test_empty_db_gives_empty_report(tmp_path):
    conn = connect(tmp_path / "t.sqlite3")
    report = build_report(conn)
    assert report["totals"]["files"] == 0
    assert report["files"] == []
    assert report["duplicates"]["group_count"] == 0
    assert report["cost"]["worst_session_tokens"] == 0
    conn.close()
