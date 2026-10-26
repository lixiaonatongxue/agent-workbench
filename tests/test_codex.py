"""Codex adapter tests on synthetic rollout files."""

import json

from app.sessions.adapters.codex import CodexAdapter


def make_codex_home(tmp_path):
    day = tmp_path / ".codex" / "sessions" / "2026" / "04" / "07"
    day.mkdir(parents=True)
    lines = [
        {"type": "session_meta", "timestamp": "2026-04-07T11:58:15.000Z",
         "payload": {"cwd": "D:/work/proj-c", "originator": "codex_cli"}},
        {"type": "event_msg", "timestamp": "2026-04-07T11:58:16.000Z",
         "payload": {"type": "task_started"}},
        {"type": "response_item", "timestamp": "2026-04-07T11:58:17.000Z",
         "payload": {"type": "message", "role": "developer",
                     "content": [{"type": "input_text", "text": "<permissions instructions>"}]}},
        {"type": "response_item", "timestamp": "2026-04-07T11:58:18.000Z",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text",
                                  "text": "<environment_context>\n  <cwd>D:/x</cwd>\n"}]}},
        {"type": "turn_context", "timestamp": "2026-04-07T11:58:19.000Z",
         "payload": {"cwd": "D:/work/proj-c", "model": "gpt-5"}},
        {"type": "response_item", "timestamp": "2026-04-07T11:58:20.000Z",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "帮我看看 nginx 配置"}]}},
        {"type": "response_item", "timestamp": "2026-04-07T11:59:00.000Z",
         "payload": {"type": "function_call", "name": "shell",
                     "arguments": "{\"command\": [\"cat\", \"nginx.conf\"]}"}},
        {"type": "response_item", "timestamp": "2026-04-07T11:59:30.000Z",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "配置看起来没问题"}]}},
    ]
    f = day / "rollout-2026-04-07T11-58-15-019d6617-49d7-7402-aea7-3ca01683a4e0.jsonl"
    f.write_text("\n".join(json.dumps(ln) for ln in lines), encoding="utf-8")
    # an empty file should be ignored by sources()
    (day / "rollout-2026-04-07T12-00-00-00000000-0000-0000-0000-000000000000.jsonl").write_text("")
    return tmp_path


def test_codex_adapter(tmp_path):
    home = make_codex_home(tmp_path)
    adapter = CodexAdapter(user_home=home)
    sources = adapter.sources()
    assert len(sources) == 1  # empty rollout skipped

    sessions = adapter.parse_source(sources[0])
    assert len(sessions) == 1
    s = sessions[0]
    assert s.agent == "codex"
    assert s.external_id == "019d6617-49d7-7402-aea7-3ca01683a4e0"
    assert s.project == "proj-c"
    assert "nginx" in (s.title or "")

    roles = [m.role for m in s.messages]
    # developer + <wrapped> user context skipped; tool call kept as tool msg
    assert roles == ["user", "tool", "assistant"]
    assert "[tool] shell(" in s.messages[1].content
    assert s.messages[2].content == "配置看起来没问题"
    assert s.started_at > 0 and s.ended_at > s.started_at


def test_codex_no_dir(tmp_path):
    adapter = CodexAdapter(user_home=tmp_path)
    assert adapter.sources() == []
