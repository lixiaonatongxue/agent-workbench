"""FastAPI server. Binds 127.0.0.1 only — this is a local, single-user tool."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import app.db as db
from app.doctor.analyze import build_report
from app.scan.rulefiles import RuleScanner

app = FastAPI(title="Agent Workbench", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8801", "http://localhost:8801"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ScanJobManager:
    """Runs at most one scan in a background thread; exposes progress status."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.status: dict = {
            "running": False, "phase": "", "done": 0, "total": 0,
            "message": "", "error": None, "files_found": 0, "finished_at": None,
        }

    def start(self, roots: list[str], include_global: bool,
              user_home: str | None) -> bool:
        with self._lock:
            if self.status["running"]:
                return False
            self.status.update({
                "running": True, "phase": "starting", "done": 0, "total": 0,
                "message": "", "error": None, "files_found": 0, "finished_at": None,
            })
            self._thread = threading.Thread(
                target=self._run, args=(roots, include_global, user_home), daemon=True)
            self._thread.start()
            return True

    def join(self, timeout: float = 600.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self, roots: list[str], include_global: bool,
             user_home: str | None) -> None:
        conn = db.connect()
        try:
            def progress(phase: str, done: int, total: int, message: str) -> None:
                self.status.update(phase=phase, done=done, total=total, message=message)

            scanner = RuleScanner()
            files, repos = scanner.scan(
                roots, include_global=include_global, user_home=user_home,
                progress=progress)
            db.save_scan(conn, files, repos, roots)
            self.status.update(
                files_found=len(files), phase="done",
                message=f"indexed {len(files)} rule files in {len(repos)} repos")
        except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
            self.status.update(error=f"{type(exc).__name__}: {exc}",
                               message="scan failed")
        finally:
            self.status.update(running=False, finished_at=_utcnow_iso())
            conn.close()


scan_jobs = ScanJobManager()


class ScanRequest(BaseModel):
    roots: list[str] = Field(min_length=1)
    include_global: bool = True
    user_home: str | None = None
    wait: bool = False  # tests and CLI-friendly synchronous mode


class SettingsUpdate(BaseModel):
    sessions_per_day: int | None = None
    price_per_mtok: float | None = None
    currency: str | None = None
    stale_days: int | None = None
    repo_active_days: int | None = None
    cjk_ratio: float | None = None
    other_ratio: float | None = None


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


@app.post("/api/scan")
def start_scan(req: ScanRequest) -> dict:
    roots = [r for r in (root.strip() for root in req.roots) if r]
    if not roots:
        raise HTTPException(status_code=400, detail="no scan roots given")
    for root in roots:
        if not Path(root).exists():
            raise HTTPException(status_code=400, detail=f"root does not exist: {root}")
    started = scan_jobs.start(roots, req.include_global, req.user_home)
    if not started:
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
def clear_index() -> dict:
    """Privacy switch: wipe all indexed rule content (settings are kept)."""
    if scan_jobs.status["running"]:
        raise HTTPException(status_code=409, detail="scan is running")
    conn = db.connect()
    try:
        db.wipe_scan_data(conn)
    finally:
        conn.close()
    return {"ok": True}


# Serve the built SPA when present (dev mode uses vite on :8801 with proxy).
_web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8800)
