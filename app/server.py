"""FastAPI server. Binds 127.0.0.1 only — this is a local, single-user tool."""

from __future__ import annotations

import threading
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import app.db as db
from app.doctor.analyze import build_report
from app.scan.rulefiles import RuleScanner
from app.sessions import indexer, query
from app.sessions.export import export_session_markdown
from app.sessions.stats import build_stats

app = FastAPI(title="Agent Workbench", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8801", "http://localhost:8801"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobManager:
    """Runs at most one callable in a background thread; exposes progress."""

    def __init__(self, result_key: str = "result") -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.result_key = result_key
        self.status: dict = {
            "running": False, "phase": "", "done": 0, "total": 0,
            "message": "", "error": None, "result": None, "finished_at": None,
        }

    def start(self, target: Callable, *args) -> bool:
        with self._lock:
            if self.status["running"]:
                return False
            self.status.update({
                "running": True, "phase": "starting", "done": 0, "total": 0,
                "message": "", "error": None, self.result_key: None,
                "finished_at": None,
            })
            self._thread = threading.Thread(
                target=self._run, args=(target, args), daemon=True)
            self._thread.start()
            return True

    def join(self, timeout: float = 900.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self, target: Callable, args: tuple) -> None:
        def progress(phase: str, done: int, total: int, message: str) -> None:
            self.status.update(phase=phase, done=done, total=total, message=message)

        try:
            result = target(*args, progress=progress)
            self.status.update(result=result, message="done")
        except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
            self.status.update(error=f"{type(exc).__name__}: {exc}",
                               message="failed")
        finally:
            self.status.update(running=False, finished_at=_utcnow_iso())


def _run_scan(roots: list[str], include_global: bool, user_home: str | None,
              progress: Callable | None = None) -> dict:
    scanner = RuleScanner()
    files, repos = scanner.scan(
        roots, include_global=include_global, user_home=user_home,
        progress=progress)
    conn = db.connect()
    try:
        db.save_scan(conn, files, repos, roots)
    finally:
        conn.close()
    return {"files": len(files), "repos": len(repos)}


def _run_session_index(force: bool, user_home: str | None,
                       progress: Callable | None = None) -> dict:
    conn = db.connect()
    try:
        return indexer.index_sessions(
            conn, adapters=indexer.default_adapters(user_home),
            force=force, progress=progress)
    finally:
        conn.close()


scan_jobs = JobManager()
session_jobs = JobManager()


class ScanRequest(BaseModel):
    roots: list[str] = Field(min_length=1)
    include_global: bool = True
    user_home: str | None = None
    wait: bool = False  # tests and CLI-friendly synchronous mode


class SessionIndexRequest(BaseModel):
    force: bool = False
    user_home: str | None = None
    wait: bool = False


class SettingsUpdate(BaseModel):
    sessions_per_day: int | None = None
    price_per_mtok: float | None = None
    currency: str | None = None
    stale_days: int | None = None
    repo_active_days: int | None = None
    cjk_ratio: float | None = None
    other_ratio: float | None = None


# ---------------------------------------------------------------- health/util

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "app": "agent-workbench", "version": app.version}


@app.get("/api/agents")
def agents() -> dict:
    scanner = RuleScanner()
    return {"agents": [
        {"id": a["id"], "name": a["name"],
         "project_patterns": a.get("project_patterns", []),
         "global_patterns": a.get("global_patterns", [])}
        for a in scanner.agents
    ]}


# ---------------------------------------------------------------- rules doctor

@app.post("/api/scan")
def start_scan(req: ScanRequest) -> dict:
    roots = [r for r in (root.strip() for root in req.roots) if r]
    if not roots:
        raise HTTPException(status_code=400, detail="no scan roots given")
    for root in roots:
        if not Path(root).exists():
            raise HTTPException(status_code=400, detail=f"root does not exist: {root}")
    if not scan_jobs.start(_run_scan, roots, req.include_global, req.user_home):
        raise HTTPException(status_code=409, detail="a scan is already running")
    if req.wait:
        scan_jobs.join()
    return scan_jobs.status


@app.get("/api/scan/status")
def scan_status() -> dict:
    return scan_jobs.status


@app.get("/api/doctor/report")
def doctor_report() -> dict:
    conn = db.connect()
    try:
        return build_report(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------- sessions

@app.post("/api/sessions/index")
def start_session_index(req: SessionIndexRequest) -> dict:
    if not session_jobs.start(_run_session_index, req.force, req.user_home):
        raise HTTPException(status_code=409, detail="an index run is already active")
    if req.wait:
        session_jobs.join()
    return session_jobs.status


@app.get("/api/sessions/index/status")
def session_index_status() -> dict:
    return session_jobs.status


@app.get("/api/sessions")
def list_sessions(
    agent: str | None = None, project: str | None = None, q: str | None = None,
    limit: int = 50, offset: int = 0,
) -> dict:
    conn = db.connect()
    try:
        return query.list_sessions(conn, agent=agent, project=project, q=q,
                                   limit=limit, offset=offset)
    finally:
        conn.close()


@app.get("/api/sessions/filters")
def session_filters() -> dict:
    conn = db.connect()
    try:
        return query.filter_options(conn)
    finally:
        conn.close()


@app.get("/api/sessions/stats")
def session_stats() -> dict:
    conn = db.connect()
    try:
        return build_stats(conn)
    finally:
        conn.close()


@app.get("/api/sessions/search")
def session_search(q: str = Query(min_length=1), agent: str | None = None,
                   limit: int = 20) -> dict:
    conn = db.connect()
    try:
        return {"items": query.search_messages(conn, q, agent=agent, limit=limit)}
    finally:
        conn.close()


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: int) -> dict:
    conn = db.connect()
    try:
        detail = query.session_detail(conn, session_id)
    finally:
        conn.close()
    if detail is None:
        raise HTTPException(status_code=404, detail="session not found")
    return detail


@app.get("/api/sessions/{session_id}/export", response_class=PlainTextResponse)
def session_export(session_id: int, mask: bool = Query(default=False)) -> PlainTextResponse:
    conn = db.connect()
    try:
        markdown = export_session_markdown(conn, session_id, mask=mask)
    finally:
        conn.close()
    if markdown is None:
        raise HTTPException(status_code=404, detail="session not found")
    safe_title = (markdown.splitlines()[0].lstrip("# ").strip() or "session")
    filename = "".join(c if c.isalnum() or c in "-_" else "_" for c in safe_title)[:60]
    return PlainTextResponse(
        markdown, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition":
                 f"attachment; filename*=UTF-8''{urllib.parse.quote(filename + '.md')}"})


# ---------------------------------------------------------------- settings/data

@app.get("/api/settings")
def get_settings_api() -> dict:
    conn = db.connect()
    try:
        return db.get_settings(conn)
    finally:
        conn.close()


@app.put("/api/settings")
def put_settings_api(update: SettingsUpdate) -> dict:
    changes = {k: v for k, v in update.model_dump().items() if v is not None}
    conn = db.connect()
    try:
        return db.set_settings(conn, changes)
    finally:
        conn.close()


@app.delete("/api/data")
def clear_index(scope: str = Query(default="rules", pattern="^(rules|sessions|all)$")) -> dict:
    """Privacy switch: wipe indexed content. `rules`, `sessions` or `all`."""
    busy = scan_jobs.status["running"] or session_jobs.status["running"]
    if busy:
        raise HTTPException(status_code=409, detail="a background job is running")
    conn = db.connect()
    try:
        if scope in ("rules", "all"):
            db.wipe_scan_data(conn)
        if scope in ("sessions", "all"):
            db.wipe_session_data(conn)
    finally:
        conn.close()
    return {"ok": True, "scope": scope}


# Serve the built SPA when present (dev mode uses vite on :8801 with proxy).
_web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8800)
