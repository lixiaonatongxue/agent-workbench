"""Masked export + stats tests."""

import time

from app.db import connect
from app.sessions import indexer
from app.sessions.adapters import BaseAdapter
from app.sessions.export import export_session_markdown, mask_secrets
from app.sessions.models import MessageRecord, SessionRecord
from app.sessions.stats import build_stats


def test_mask_secrets():
    text = (
        "key is sk-abc123def456ghi789xyz ok\n"
        "token: ghp_abcdefghijklmnopqrstuvwxyz123456\n"
        "aws AKIAIOSFODNN7EXAMPLE\n"
        "api_key = supersecret12345 done\n"
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInTPpseudo\n"
        "safe words remain untouched"
    )
    masked = mask_secrets(text)
    assert "sk-abc123" not in masked and "sk-***MASKED***" in masked
    assert "ghp_abcdefgh" not in masked and "gh*_***MASKED***" in masked
    assert "AKIAIOSFODNN7EXAMPLE" not in masked
    assert "supersecret12345" not in masked and "api_key = ***MASKED***" in masked
    assert "eyJhbGciOiJI" not in masked
    assert "safe words remain untouched" in masked


def _seeded_conn(tmp_path):
    class FakeAdapter(BaseAdapter):
        agent_id = "fake"

        def sources(self):
            src = self.home / "fake.jsonl"
            return [src] if src.exists() else []

        def parse_source(self, source):
            now = time.time()
            return [
                SessionRecord(agent="fake", external_id="s1", project="p1",
                              project_path=None, title="t1", started_at=now - 3600,
                              ended_at=now - 3500, source_path=str(source),
                              messages=[MessageRecord("user", now - 3600, "hello sk-abc123def456ghi789")]),
                SessionRecord(agent="fake", external_id="s2", project="p2",
                              project_path=None, title="t2", started_at=now - 1800,
                              ended_at=None, source_path=str(source),
                              messages=[MessageRecord("assistant", now - 1800, "world")]),
            ]

    (tmp_path / "fake.jsonl").write_text("v1", encoding="utf-8")
    conn = connect(tmp_path / "t.sqlite3")
    indexer.index_sessions(conn, [FakeAdapter(tmp_path)])
    return conn


def test_export_mask_toggle(tmp_path):
    conn = _seeded_conn(tmp_path)
    sid = conn.execute("SELECT id FROM sessions WHERE external_id='s1'").fetchone()["id"]
    raw = export_session_markdown(conn, sid, mask=False)
    masked = export_session_markdown(conn, sid, mask=True)
    assert "sk-abc123def456ghi789" in raw
    assert "sk-abc123def456ghi789" not in masked
    assert "***MASKED***" in masked
    conn.close()


def test_build_stats(tmp_path):
    conn = _seeded_conn(tmp_path)
    stats = build_stats(conn)
    assert stats["totals"]["sessions"] == 2
    assert stats["totals"]["messages"] == 2
    assert stats["totals"]["agents"] == 1
    assert stats["totals"]["projects"] == 2
    assert stats["by_agent"][0]["agent"] == "fake"
    assert stats["by_agent"][0]["avg_messages"] == 1.0
    assert len(stats["by_month"]) == 12
    assert sum(m["sessions"] for m in stats["by_month"]) == 2
    assert {p["project"] for p in stats["top_projects"]} == {"p1", "p2"}
    conn.close()
