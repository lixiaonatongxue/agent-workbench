"""Indexer + query + export integration on synthetic adapters."""

import sqlite3

from app.db import connect
from app.sessions import indexer, query
from app.sessions.adapters import BaseAdapter
from app.sessions.export import export_session_markdown
from app.sessions.models import MessageRecord, SessionRecord


class FakeAdapter(BaseAdapter):
    agent_id = "fake"
    agent_name = "Fake"

    def __init__(self, home, mutate=None):
        super().__init__(home)
        self.mutate = mutate

    def sources(self):
        src = self.home / "fake.jsonl"
        return [src] if src.exists() else []

    def parse_source(self, source):
        records = [
            SessionRecord(
                agent=self.agent_id, external_id="sess-1", project="proj-x",
                project_path="D:/x", title="nginx config work",
                started_at=1700000000.0, ended_at=1700000600.0,
                source_path=str(source),
                messages=[
                    MessageRecord("user", 1700000000.0, "怎么配置 nginx 反向代理"),
                    MessageRecord("assistant", 1700000100.0,
                                  "proxy_pass 即可\n[tool] Write(nginx.conf)"),
                ]),
        ]
        if self.mutate:
            self.mutate(records)
        return records


def test_index_search_export_roundtrip(tmp_path):
    (tmp_path / "fake.jsonl").write_text("v1", encoding="utf-8")
    conn = connect(tmp_path / "t.sqlite3")
    stats = indexer.index_sessions(conn, [FakeAdapter(tmp_path)])
    assert stats["sessions"] == 1 and stats["messages"] == 2

    listed = query.list_sessions(conn)
    assert listed["total"] == 1
    item = listed["items"][0]
    assert item["project"] == "proj-x"

    hits = query.list_sessions(conn, q="nginx")
    assert hits["total"] == 1
    assert "nginx" in hits["items"][0]["snippet"]

    detail = query.session_detail(conn, item["id"])
    assert len(detail["messages"]) == 2

    md = export_session_markdown(conn, item["id"])
    assert "nginx config work" in md
    assert "proxy_pass" in md
    assert "[tool] Write(nginx.conf)" in md

    # re-index without changes: skipped by mtime
    stats2 = indexer.index_sessions(conn, [FakeAdapter(tmp_path)])
    assert stats2["sources_indexed"] == 0
    assert query.list_sessions(conn)["total"] == 1
    conn.close()


def test_reindex_updates_and_removes(tmp_path):
    src = tmp_path / "fake.jsonl"
    src.write_text("v1", encoding="utf-8")
    conn = connect(tmp_path / "t.sqlite3")
    state = {"drop": False}
    adapter = FakeAdapter(tmp_path, mutate=lambda recs: recs.clear()
                          if state["drop"] else recs.extend([
                              SessionRecord(
                                  agent="fake", external_id="sess-2",
                                  project="proj-y", project_path=None, title=None,
                                  started_at=1700001000.0, ended_at=None,
                                  source_path=recs[0].source_path,
                                  messages=[MessageRecord("user", 1700001000.0,
                                                          "第二个会话")])]))

    indexer.index_sessions(conn, [adapter])
    assert query.list_sessions(conn)["total"] == 2

    # touch source file so mtime changes, sessions replaced
    src.write_text("changed", encoding="utf-8")
    indexer.index_sessions(conn, [adapter])
    assert query.list_sessions(conn)["total"] == 2

    # next run yields nothing -> its sessions disappear
    state["drop"] = True
    src.write_text("changed again", encoding="utf-8")
    indexer.index_sessions(conn, [adapter])
    assert query.list_sessions(conn)["total"] == 0
    # FTS index is consistent with the empty table
    assert query.list_sessions(conn, q="nginx")["total"] == 0
    conn.close()


def test_search_filters_and_options(tmp_path):
    (tmp_path / "fake.jsonl").write_text("v1", encoding="utf-8")
    conn = connect(tmp_path / "t.sqlite3")
    indexer.index_sessions(conn, [FakeAdapter(tmp_path)])
    assert query.list_sessions(conn, agent="other")["total"] == 0
    opts = query.filter_options(conn)
    assert opts["agents"] == [{"id": "fake", "count": 1}]
    assert opts["projects"] == ["proj-x"]
    msgs = query.search_messages(conn, "反向代理")
    assert len(msgs) == 1 and msgs[0]["project"] == "proj-x"
    conn.close()
