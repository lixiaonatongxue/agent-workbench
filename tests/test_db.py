import sqlite3

from app.db import connect, get_settings, set_settings


def test_schema_created(tmp_path):
    conn = connect(tmp_path / "t.sqlite3")
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"repos", "rule_files", "rule_blocks", "scan_runs", "settings"} <= tables
    conn.close()


def test_settings_roundtrip_and_defaults(tmp_path):
    conn = connect(tmp_path / "t.sqlite3")
    assert get_settings(conn)["sessions_per_day"] == 10
    merged = set_settings(conn, {"sessions_per_day": 25, "price_per_mtok": 22.5})
    assert merged["sessions_per_day"] == 25
    assert merged["price_per_mtok"] == 22.5
    # persists across connections
    conn.close()
    conn2 = connect(tmp_path / "t.sqlite3")
    assert get_settings(conn2)["sessions_per_day"] == 25
    conn2.close()


def test_settings_ignores_unknown_and_bad_values(tmp_path):
    conn = connect(tmp_path / "t.sqlite3")
    merged = set_settings(conn, {"evil_key": "x", "sessions_per_day": "not-a-number"})
    assert "evil_key" not in merged
    assert merged["sessions_per_day"] == 10  # kept default on bad value
    conn.close()


def test_save_and_wipe(tmp_path):
    from app.scan.rulefiles import RuleScanner
    from app.db import save_scan, wipe_scan_data

    repo = tmp_path / "proj"
    (repo / ".git").mkdir(parents=True)
    (repo / "AGENTS.md").write_text(
        "# Rules\n\nAlways run the full test suite before every single commit.\n")

    scanner = RuleScanner()
    files, repos = scanner.scan([str(tmp_path)], include_global=False)
    conn = connect(tmp_path / "t.sqlite3")
    save_scan(conn, files, repos, [str(tmp_path)])
    assert conn.execute("SELECT COUNT(*) FROM rule_files").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM rule_blocks").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0] == 1

    wipe_scan_data(conn)
    assert conn.execute("SELECT COUNT(*) FROM rule_files").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0] == 0
    # settings survive a wipe
    assert get_settings(conn)["sessions_per_day"] == 10
    conn.close()
