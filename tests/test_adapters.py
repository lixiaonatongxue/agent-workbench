"""Adapter tests on fully synthetic fixtures (no real personal data)."""

import json
import sqlite3

from app.sessions.adapters.claude_code import ClaudeCodeAdapter
from app.sessions.adapters.zcode import ZcodeAdapter


def make_zcode_db(path):
    conn = sqlite3.connect(str(path))
    conn.executescript("""
    CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, title TEXT,
        time_created INTEGER, time_updated INTEGER, time_deleted INTEGER);
    CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT,
        time_created INTEGER, sequence INTEGER, data TEXT);
    CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
        time_created INTEGER, time_updated INTEGER, sequence INTEGER, data TEXT);
    """)
    conn.execute(
        "INSERT INTO session VALUES ('s1', 'D:/work/proj-a', '搭建 nginx 配置', 1700000000000, 1700000500000, NULL)")
    conn.execute(
        "INSERT INTO session VALUES ('s2', 'D:/work/proj-b', 'deleted one', 1, 2, 1700000099999)")  # deleted
    msgs = [
        ("m1", "s1", 1700000001000, 0, "user", "user_prompt",
         [{"type": "text", "text": "帮我写一个 nginx 反向代理配置"}]),
        ("m2", "s1", 1700000010000, 1, "assistant", "assistant_response",
         [{"type": "text", "text": "好的，配置如下："},
          {"type": "tool", "tool": "Write", "state": {"input": {"path": "nginx.conf"}}},
          {"type": "reasoning", "text": "internal thinking, should be skipped"}]),
        ("m3", "s1", 1700000020000, 2, "user", "todo_reminder",
         [{"type": "text", "text": "reminder noise not indexed"}]),
    ]
    for mid, sid, ts, seq, role, kind, parts in msgs:
        conn.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?, ?)",
            (mid, sid, ts, seq, json.dumps({"role": role,
                                            "semantics": {"kind": kind}})))
        for i, p in enumerate(parts):
            conn.execute(
                "INSERT INTO part VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"{mid}-p{i}", mid, sid, ts, ts, i, json.dumps(p)))
    conn.commit()
    conn.close()
    return path


def test_zcode_adapter(tmp_path):
    db = make_zcode_db(tmp_path / "db.sqlite")
    adapter = ZcodeAdapter(user_home=tmp_path)
    # adapter looks under <home>/.zcode/cli/db/db.sqlite
    target = tmp_path / ".zcode" / "cli" / "db"
    target.mkdir(parents=True)
    db.rename(target / "db.sqlite")

    sources = adapter.sources()
    assert len(sources) == 1
    sessions = adapter.parse_source(sources[0])
    assert len(sessions) == 1  # deleted session dropped
    s = sessions[0]
    assert s.agent == "zcode"
    assert s.external_id == "s1"
    assert s.project == "proj-a"
    assert s.title == "搭建 nginx 配置"
    assert s.started_at == 1700000000.0
    assert len(s.messages) == 2  # reminder kind skipped
    assert s.messages[0].role == "user"
    assert "nginx" in s.messages[0].content
    assistant = s.messages[1]
    assert "[tool] Write(" in assistant.content
    assert "internal thinking" not in assistant.content


def make_claude_home(tmp_path):
    projects = tmp_path / ".claude" / "projects" / "D--work-projA"
    projects.mkdir(parents=True)
    lines = [
        {"type": "user", "isSidechain": False, "cwd": "D:\\work\\projA",
         "timestamp": "2026-01-02T10:00:00.000Z",
         "message": {"role": "user", "content": "如何配置 nginx 负载均衡"}},
        {"type": "assistant", "isSidechain": False, "cwd": "D:\\work\\projA",
         "timestamp": "2026-01-02T10:00:30.000Z",
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": "用 upstream 配置即可"},
             {"type": "tool_use", "name": "WebSearch", "input": {"query": "nginx upstream"}},
         ]}},
        {"type": "user", "isSidechain": True, "cwd": "D:\\work\\projA",
         "timestamp": "2026-01-02T10:01:00.000Z",
         "message": {"role": "user", "content": "sidechain should be skipped"}},
        {"type": "summary", "isSidechain": False,
         "summary": "session summary line"},
        {"type": "user", "isSidechain": False, "cwd": "D:\\work\\projA",
         "timestamp": "2026-01-02T10:02:00.000Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "content": "search results here"}]}},
    ]
    f = projects / "abc-123.jsonl"
    f.write_text("\n".join(json.dumps(ln) for ln in lines), encoding="utf-8")
    return tmp_path


def test_claude_adapter(tmp_path):
    home = make_claude_home(tmp_path)
    adapter = ClaudeCodeAdapter(user_home=home)
    sources = adapter.sources()
    assert [s.name for s in sources] == ["abc-123.jsonl"]
    sessions = adapter.parse_source(sources[0])
    assert len(sessions) == 1
    s = sessions[0]
    assert s.agent == "claude-code"
    assert s.external_id == "abc-123"
    assert s.project == "projA"
    assert "nginx" in (s.title or "")
    assert len(s.messages) == 3  # sidechain + summary skipped
    assert s.messages[0].role == "user"
    assert s.messages[1].content.startswith("用 upstream")
    assert "[tool] WebSearch(" in s.messages[1].content
    assert "[tool_result] search results here" in s.messages[2].content
    assert s.started_at > 0 and s.ended_at >= s.started_at
