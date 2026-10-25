"""SQLite persistence for scan results and settings.

Stdlib sqlite3 only. All personal data (rule contents, block text) stays in
this local file; it is gitignored and can be wiped via the API at any time.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import app.paths as paths
from app.scan.repos import RepoInfo
from app.scan.rulefiles import RuleFileInfo

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    path TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    last_activity REAL
);
CREATE TABLE IF NOT EXISTS rule_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    repo TEXT,
    agents TEXT NOT NULL,
    size INTEGER,
    lines INTEGER,
    chars INTEGER,
    cjk_chars INTEGER,
    tokens_est INTEGER,
    mtime REAL,
    content_hash TEXT,
    error TEXT,
    scanned_at TEXT
);
CREATE TABLE IF NOT EXISTS rule_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES rule_files(id) ON DELETE CASCADE,
    start_line INTEGER,
    end_line INTEGER,
    text TEXT,
    tokens_est INTEGER,
    simhash INTEGER,
    norm_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_blocks_file ON rule_blocks(file_id);
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    roots TEXT,
    file_count INTEGER,
    error TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

DEFAULT_SETTINGS = {
    "sessions_per_day": 10,     # assumed coding-agent sessions per day
    "price_per_mtok": 15.0,     # currency units per 1M input tokens
    "currency": "CNY",
    "stale_days": 180,          # rule file untouched this long => suspicious
    "repo_active_days": 30,     # repo committed within this window => active
    "cjk_ratio": 1.8,
    "other_ratio": 3.5,
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_file: str | Path | None = None) -> sqlite3.Connection:
    p = Path(db_file) if db_file else paths.db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def get_settings(conn: sqlite3.Connection) -> dict:
    merged = dict(DEFAULT_SETTINGS)
    for row in conn.execute("SELECT key, value FROM settings"):
        key = row["key"]
        if key in merged:
            default = merged[key]
            try:
                merged[key] = type(default)(row["value"])
            except (TypeError, ValueError):
                pass  # keep default on bad value
    return merged


def set_settings(conn: sqlite3.Connection, updates: dict) -> dict:
    current = get_settings(conn)
    with conn:
        for key, value in updates.items():
            if key not in DEFAULT_SETTINGS:
                continue  # unknown keys are ignored
            if not isinstance(value, type(DEFAULT_SETTINGS[key])):
                try:
                    value = type(DEFAULT_SETTINGS[key])(value)
                except (TypeError, ValueError):
                    continue
            current[key] = value
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
    return current


def save_scan(conn: sqlite3.Connection, files: list[RuleFileInfo],
              repos: list[RepoInfo], roots: list[str]) -> None:
    """Replace stored scan with the given results (latest scan wins)."""
    now = _utcnow_iso()
    with conn:
        conn.execute("DELETE FROM rule_blocks")
        conn.execute("DELETE FROM rule_files")
        conn.execute("DELETE FROM repos")
        for repo in repos:
            conn.execute(
                "INSERT OR REPLACE INTO repos(path, name, last_activity) VALUES (?, ?, ?)",
                (repo.path, repo.name, repo.last_activity),
            )
        for f in files:
            cur = conn.execute(
                "INSERT INTO rule_files(path, repo, agents, size, lines, chars, cjk_chars,"
                " tokens_est, mtime, content_hash, error, scanned_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f.path, f.repo, json.dumps(f.agents), f.size, f.lines, f.chars,
                 f.cjk_chars, f.tokens_est, f.mtime, f.content_hash, f.error, now),
            )
            file_id = cur.lastrowid
            for b in f.blocks:
                unsigned = b.simhash & 0xFFFFFFFFFFFFFFFF
                signed = unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned
                conn.execute(
                    "INSERT INTO rule_blocks(file_id, start_line, end_line, text,"
                    " tokens_est, simhash, norm_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (file_id, b.start_line, b.end_line, b.text, b.tokens_est,
                     signed, b.norm_hash),
                )
        conn.execute(
            "INSERT INTO scan_runs(started_at, finished_at, roots, file_count)"
            " VALUES (?, ?, ?, ?)",
            (now, now, json.dumps(roots), len(files)),
        )


def wipe_scan_data(conn: sqlite3.Connection) -> None:
    """Privacy switch: drop all scanned rule content from the local index."""
    with conn:
        conn.execute("DELETE FROM rule_blocks")
        conn.execute("DELETE FROM rule_files")
        conn.execute("DELETE FROM repos")
        conn.execute("DELETE FROM scan_runs")
