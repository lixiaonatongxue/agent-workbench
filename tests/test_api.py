"""API tests against synthetic trees via TestClient."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKBENCH_HOME", str(tmp_path / "awhome"))
    from app.server import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def scanned_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKBENCH_HOME", str(tmp_path / "awhome"))
    repo = tmp_path / "proj"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (repo / "CLAUDE.md").write_text(
        "# Rules\n\nAlways run the full test suite before every single commit.\n")
    home = tmp_path / "fakehome"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "AGENTS.md").write_text(
        "# Global agent rules\n\nAnswer concisely and prefer standard library code.\n")
    from app.server import app
    with TestClient(app) as c:
        resp = c.post("/api/scan", json={
            "roots": [str(tmp_path)], "include_global": True,
            "user_home": str(home), "wait": True,
        })
        assert resp.status_code == 200
        assert resp.json()["error"] is None
        yield c


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_agents_endpoint(client):
    resp = client.get("/api/agents")
    ids = {a["id"] for a in resp.json()["agents"]}
    assert {"claude-code", "codex", "zcode", "cursor"} <= ids


def test_scan_rejects_missing_root(client):
    resp = client.post("/api/scan", json={"roots": ["Z:/definitely/not/here"]})
    assert resp.status_code == 400


def test_report_after_scan(scanned_client):
    resp = scanned_client.get("/api/doctor/report")
    assert resp.status_code == 200
    report = resp.json()
    assert report["totals"]["files"] == 2
    agents_seen = {a for f in report["files"] for a in f["agents"]}
    assert agents_seen == {"Claude Code", "Codex"}  # zcode has no matching file here
    per_agent = {a["name"]: a for a in report["per_agent"]}
    assert per_agent["Codex"]["global_tokens"] > 0
    assert report["cost"]["worst_session_tokens"] > 0


def test_settings_roundtrip(client):
    resp = client.put("/api/settings", json={"sessions_per_day": 7, "price_per_mtok": 3.0})
    assert resp.status_code == 200
    assert resp.json()["sessions_per_day"] == 7
    assert client.get("/api/settings").json()["price_per_mtok"] == 3.0


def test_clear_data_wipes_report(scanned_client):
    assert scanned_client.delete("/api/data").status_code == 200
    report = scanned_client.get("/api/doctor/report").json()
    assert report["totals"]["files"] == 0
    # settings survive
    assert scanned_client.get("/api/settings").json()["sessions_per_day"] == 10


def test_scan_status_shape(client):
    status = client.get("/api/scan/status").json()
    assert {"running", "phase", "done", "total", "message", "error"} <= set(status)
