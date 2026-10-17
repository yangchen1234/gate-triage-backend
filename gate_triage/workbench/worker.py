"""Durable job worker and persisted server-side simulation clock.

The queue lives in SQL, not a request background callback. Leases and compare-
and-set claims make queued or interrupted jobs recoverable after restart.
"""
from __future__ import annotations

import copy
import csv
import html
import io
import json
import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from .db import Job, Workspace, get_database, utcnow

log = logging.getLogger(__name__)
_thread: threading.Thread | None = None
_stop = threading.Event()
_wake = threading.Event()
_last_tick: str | None = None
_owner = str(uuid.uuid4())


def notify_worker() -> None:
    _wake.set()


def worker_status() -> dict:
    return {"running": bool(_thread and _thread.is_alive()), "last_tick_at": _last_tick, "queue": "durable_sql", "playback": "server_clock"}


def start_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    # A browser must explicitly resume after a process restart. The synthetic
    # world never silently advances for downtime or catches up to wall time.
    from .api import audit
    database = get_database()
    with database.write_lock, database.session() as session:
        for workspace in session.scalars(select(Workspace)):
            if (workspace.playback or {}).get("playing"):
                workspace.playback = {**workspace.playback, "playing": False, "status": "paused", "paused_reason": "server_restarted"}
                workspace.revision += 1
                audit(session, workspace, "playback.paused", {"reason": "server_restarted"}, "system")
    _thread = threading.Thread(target=_run, name="gate-triage-durable-worker", daemon=True)
    _thread.start()


def stop_worker() -> None:
    _stop.set()
    _wake.set()
    if _thread:
        _thread.join(timeout=5)


def _claim() -> dict | None:
    database = get_database()
    with database.write_lock, database.session() as session:
        now = utcnow()
        statement = select(Job).where(or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now))).order_by(Job.created_at).limit(1).with_for_update(skip_locked=True)
        job = session.scalar(statement)
        if not job:
            return None
        if job.attempts >= 3:
            job.status = "failed"
            job.error = {"code": "JOB_RETRY_EXHAUSTED", "message": "This interrupted job exhausted its automatic retries. Submit a new request.", "retryable": False}
            job.finished_at = now
            return None
        claimed = session.execute(update(Job).where(Job.id == job.id, or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now))).values(status="running", lease_owner=_owner, lease_until=now + timedelta(seconds=120), attempts=job.attempts + 1, progress=10, started_at=now), execution_options={"synchronize_session": False})
        if claimed.rowcount != 1:
            return None
        return {"id": job.id, "workspace_id": job.workspace_id, "kind": job.kind, "payload": copy.deepcopy(job.payload), "state": copy.deepcopy(job.state_snapshot), "input_revision": job.input_revision}


def _execute(job: dict) -> dict:
    from .api import engine
    payload = job["payload"]
    if job["kind"] == "plan":
        result = engine().plan(job["state"], profile=payload.get("profile", "throughput"), strategy=payload.get("strategy", "optimized"))
        return {**result, "id": job["id"], "plan_id": job["id"], "input_revision": job["input_revision"], "scope": "simulation_cohort_only"}
    if job["kind"] == "experiment":
        result = engine().experiment(payload["scenario_id"], seeds=payload.get("seeds", [17, 29, 43]), horizon_minutes=payload.get("horizon_minutes", 240))
        return {**result, "id": job["id"], "experiment_id": job["id"], "input_revision": job["input_revision"], "scope": "simulation_cohort_only"}
    if job["kind"] == "export":
        content = payload.get("subject_result") or {"snapshot": engine().snapshot(job["state"]), "input_revision": job["input_revision"], "label": "Synthetic rehearsal handoff", "scope": "simulation_cohort_only"}
        fmt = payload.get("format", "json")
        if fmt == "json":
            rendered, mime = json.dumps(content, indent=2, default=str), "application/json"
        elif fmt == "html":
            rendered = "<!doctype html><meta charset='utf-8'><title>Gate Triage rehearsal report</title><h1>Gate Triage rehearsal report</h1><p>Synthetic data · no physical execution authority</p><pre>" + html.escape(json.dumps(content, indent=2, default=str)) + "</pre>"
            mime = "text/html"
        else:
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(["field", "value"])
            for key, value in content.items():
                cell = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
                # Prevent formulas if the exported file is opened in Excel.
                if cell.startswith(("=", "+", "-", "@")):
                    cell = "'" + cell
                writer.writerow([key, cell])
            rendered, mime = stream.getvalue(), "text/csv"
        return {"artifact_id": job["id"], "filename": f"gate-triage-{payload.get('subject_type', 'handoff')}.{fmt}", "mime_type": mime, "format": fmt, "content": rendered, "scope": "simulation_cohort_only"}
    raise ValueError("Unsupported durable job type")


def _finish(job: dict, future: Future) -> None:
    from .api import audit, serializable
    database = get_database()
    try:
        result = serializable(future.result())
        error = None
    except Exception:
        log.exception("Workbench job failed (kind=%s)", job["kind"])
        result = None
        error = {"code": "JOB_FAILED", "message": "The computation could not finish. The workspace is unchanged; submit a new request or inspect server logs.", "retryable": True}
    with database.write_lock, database.session() as session:
        row = session.get(Job, job["id"])
        if not row or row.lease_owner != _owner or row.status != "running":
            return
        row.status = "failed" if error else "succeeded"
        row.result = result
        row.error = error
        row.progress = 100
        row.finished_at = utcnow()
        row.lease_until = None
        workspace = session.get(Workspace, row.workspace_id)
        if workspace:
            audit(session, workspace, f"{row.kind}.{row.status}", {"job_id": row.id, "input_revision": row.input_revision, "current_revision": workspace.revision}, "worker")


def _playback_tick() -> None:
    from .api import audit, commit_state, engine
    database = get_database()
    with database.write_lock, database.session() as session:
        for workspace in session.scalars(select(Workspace).where(Workspace.mode == "SIMULATION").with_for_update(skip_locked=True)):
            playback = dict(workspace.playback or {})
            if not playback.get("playing"):
                continue
            last = datetime.fromisoformat(playback.get("last_tick_at", utcnow().isoformat()))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (utcnow() - last).total_seconds()
            tick_minutes = int(playback.get("tick_minutes", 1))
            speed = float(playback.get("speed", 1))
            # Publish at most once per second, batching virtual minutes at
            # higher speeds. This keeps the SQL projection and UI revision
            # stream responsive without generating dozens of writes/second.
            if elapsed < max(1.0, tick_minutes / speed):
                continue
            now_min = int(workspace.state.get("clock_min", 0))
            horizon = int(workspace.state.get("horizon_minutes", 240))
            remaining = horizon - now_min
            if remaining <= 0:
                workspace.playback = {**playback, "playing": False, "status": "finished", "paused_reason": "horizon_reached", "last_tick_at": utcnow().isoformat()}
                workspace.revision += 1
                audit(session, workspace, "playback.finished", {"clock_min": now_min}, "worker")
                continue
            # A bounded tick prevents one overloaded process from jumping past
            # several operational decisions to catch up with wall-clock time.
            due_ticks = int(elapsed * speed / tick_minutes)
            amount = min(due_ticks * tick_minutes, 120, remaining)
            try:
                state = engine().apply_command(copy.deepcopy(workspace.state), {"command": "advance", "minutes": amount, "strategy": playback.get("strategy", "optimized"), "profile": playback.get("profile", "throughput")})
                next_tick = last + timedelta(seconds=amount / speed)
                workspace.playback = {**playback, "last_tick_at": next_tick.isoformat(), "status": "playing"}
                commit_state(session, workspace, state, "playback.advanced", {"minutes": amount, "source": "server_clock"}, "worker")
            except Exception:
                log.exception("Server playback paused after a clock error")
                workspace.playback = {**playback, "playing": False, "status": "paused", "paused_reason": "advance_failed", "last_tick_at": utcnow().isoformat()}
                workspace.revision += 1
                audit(session, workspace, "playback.paused", {"reason": "advance_failed"}, "worker")


def _run() -> None:
    global _last_tick
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gate-triage-compute")
    running: tuple[dict, Future] | None = None
    last_renewal = time.monotonic()
    try:
        while not _stop.is_set():
            _last_tick = utcnow().isoformat()
            try:
                if running and running[1].done():
                    _finish(*running)
                    running = None
                if running and time.monotonic() - last_renewal > 10:
                    with get_database().write_lock, get_database().session() as session:
                        session.execute(update(Job).where(Job.id == running[0]["id"], Job.lease_owner == _owner, Job.status == "running").values(lease_until=utcnow() + timedelta(seconds=120), progress=50))
                    last_renewal = time.monotonic()
                if running is None:
                    job = _claim()
                    if job:
                        running = (job, executor.submit(_execute, job))
                _playback_tick()
            except Exception:
                log.exception("Workbench worker loop recovered from an error")
            _wake.wait(0.25)
            _wake.clear()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
