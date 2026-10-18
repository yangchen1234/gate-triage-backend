"""Isolated, bounded demo sessions for Ryan's synthetic queue and advisory agent.

This is intentionally single-process, temporary storage. A session is a bearer
capability, not an account. Keys live in process memory only and never enter a job
record. No code here sends outreach or changes a container's release authority.
"""
from __future__ import annotations

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import hmac
import os
import re
from secrets import token_urlsafe
from threading import BoundedSemaphore, Event, RLock, Thread
from time import time
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, StrictInt, StrictStr, field_validator

from gate_triage.agent import run_agent
from gate_triage.config import Settings
from gate_triage.models import DEFAULT_SCENARIO, ScenarioPatch
from gate_triage.port_profiles import PROFILES
from gate_triage.score import score_all
from gate_triage.statistics import calculate_stats

TARIFF_NOTICE = "Synthetic demonstration assumptions, not a quote or a verified port tariff. The same 100-container fixture is reprofiled across ports; it is not live port traffic."
SESSION_TTL = 3600
KEY_TTL = 900
MAX_SESSIONS = 40
MAX_JOBS = 24


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


class ConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=16, max_length=2048, repr=False)
    model: StrictStr = Field(pattern=r"^claude-[A-Za-z0-9._-]{1,80}$")

    @field_validator("api_key")
    @classmethod
    def key_whitespace(cls, value):
        key = value.get_secret_value()
        if any(char.isspace() for char in key):
            raise ValueError("Key must not contain whitespace")
        return value


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    top_n: StrictInt = Field(default=5, ge=1, le=5)
    use_model: StrictBool = False


class TeamInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_code: SecretStr = Field(min_length=1, max_length=256, repr=False)


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    container_id: StrictStr = Field(min_length=1, max_length=32)
    blocker: StrictStr = Field(pattern="^(customs_hold|source_conflict|reefer_silent|zone_power)$")
    decision: StrictStr = Field(pattern="^(approved|rejected)$")
    note: StrictStr | None = Field(default=None, max_length=1000)


class BoundedRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def bounded(request: Request):
            # Read a bounded stream before Pydantic parses it; validation errors
            # never include submitted values (not even malformed key payloads).
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    raise HTTPException(413, "Console request is too large")
            request._body = bytes(body)
            return await handler(request)
        return bounded


@dataclass
class Session:
    token: str = field(repr=False)
    expires: float
    ip: str = field(repr=False)
    scenario: dict = field(default_factory=lambda: deepcopy(DEFAULT_SCENARIO))
    revision: int = 1
    queue: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    key: SecretStr | None = field(default=None, repr=False)
    model: str | None = None
    source: str = "none"
    key_expires: float = 0
    jobs: dict = field(default_factory=dict)
    idempotency: dict = field(default_factory=dict)
    active_job: str | None = None
    model_jobs: int = 0
    calls: deque = field(default_factory=deque)
    cancel: Event = field(default_factory=Event, repr=False)


class ConsoleStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.raw = json.loads(settings.containers_file.read_text(encoding="utf-8"))
        self.sessions: dict[str, Session] = {}
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="console-plan")
        self._model_slots = BoundedSemaphore(2)
        self._created = defaultdict(deque)
        self._model_ips = defaultdict(deque)
        self._team_attempts = defaultdict(deque)
        # Render injects these at runtime. A provider key alone never enables
        # public spending; an explicit model and a strong private gate are required.
        self._server_key = None
        self._server_model = None
        self._team_code = None
        workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "")
        self._server_workspace = workspace if re.fullmatch(r"wrkspc_[A-Za-z0-9]{8,80}", workspace) else None
        key = os.getenv("ANTHROPIC_API_KEY", "")
        model = os.getenv("ANTHROPIC_MODEL", "")
        code = os.getenv("CONSOLE_TEAM_ACCESS_CODE", "")
        if (16 <= len(key) <= 2048 and not any(c.isspace() for c in key)
                and re.fullmatch(r"claude-[A-Za-z0-9._-]{1,80}", model)
                and 16 <= len(code) <= 256 and not any(c.isspace() for c in code)):
            self._server_key = SecretStr(key)
            self._server_model = model
            self._team_code = SecretStr(code)
        self._stop = Event()
        self._sweeper = Thread(target=self._sweep, daemon=True, name="console-key-expiry")
        self._sweeper.start()

    def _sweep(self):
        while not self._stop.wait(15):
            with self._lock:
                self._cleanup()

    def _cleanup(self):
        now = time()
        for token, session in list(self.sessions.items()):
            if session.expires <= now:
                self._erase(session)
                del self.sessions[token]
            elif (session.key is not None or session.source == "render_environment") and session.key_expires <= now:
                self._erase(session)
        for history in (self._created, self._model_ips, self._team_attempts):
            for ip, stamps in list(history.items()):
                while stamps and stamps[0] <= now - 3600:
                    stamps.popleft()
                if not stamps:
                    del history[ip]

    @staticmethod
    def _erase(session):
        session.key = None
        session.model = None
        session.source = "none"
        session.key_expires = 0
        session.cancel.set()

    def close(self):
        self._stop.set()
        with self._lock:
            for session in self.sessions.values():
                self._erase(session)
            self.sessions.clear()
            self._server_key = None
            self._team_code = None
            self._server_model = None
            self._server_workspace = None
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._sweeper.join(timeout=1)

    def _get(self, token):
        self._cleanup()
        if not token or len(token) > 128 or token not in self.sessions:
            raise HTTPException(401, "Console session expired or invalid; create a new session")
        return self.sessions[token]

    def _rebuild(self, session):
        queue = score_all(self.raw, session.scenario)
        by_id = {row["container_id"]: row for row in queue}
        input_order = [by_id[row["container_id"]] for row in self.raw]
        stats = calculate_stats(input_order, session.scenario,
                                containers_per_lane_per_day=self.settings.containers_per_lane_per_day)
        stats.update({"currency": PROFILES[session.scenario["port"]]["currency"],
                      "gate_capacity_today": session.scenario["lanes_open"] * self.settings.containers_per_lane_per_day,
                      "eligible_for_release": sum(row["action"] == "release" for row in queue),
                      "comparison_notice": "FIFO/priority fee comparison allocates all rows to abstract capacity; it is not an executable release schedule."})
        session.queue, session.stats = queue, stats

    def _snapshot(self, session, include_token=False):
        result = {"revision": session.revision, "scenario": deepcopy(session.scenario),
                  "queue": deepcopy(session.queue), "stats": deepcopy(session.stats),
                  "model": self._model_meta(session), "expires_at": _iso(session.expires),
                  "data_kind": "synthetic", "tariff_notice": TARIFF_NOTICE}
        if include_token:
            result["token"] = session.token
        return result

    def _server_available(self):
        return self._server_key is not None and self._team_code is not None and self._server_model is not None

    def _model_meta(self, session):
        authorized = session.key is not None or (session.source == "render_environment" and self._server_available())
        return {"configured": authorized,
                "model": session.model if authorized else self._server_model if self._server_available() else None,
                "key_expires_at": _iso(session.key_expires) if authorized else None,
                "provider": "anthropic", "server_available": self._server_available(),
                "source": session.source if authorized else "none",
                "storage": "render_environment" if authorized and session.source == "render_environment" else "process_memory_only"}

    @staticmethod
    def _check_revision(session, revision):
        if revision != str(session.revision) and revision != f'"{session.revision}"':
            if revision is None:
                raise HTTPException(428, "If-Match scenario revision is required")
            raise HTTPException(409, "Scenario changed; refresh session before continuing")

    def create(self, ip):
        with self._lock:
            self._cleanup()
            stamps = self._created[ip]
            now = time()
            if sum(stamp > now - 60 for stamp in stamps) >= 6 or len(stamps) >= 30:
                raise HTTPException(429, "Session creation limit reached; try again later", headers={"Retry-After": "60"})
            if len(self.sessions) >= MAX_SESSIONS:
                raise HTTPException(503, "Demo session capacity reached; retry after an active session ends")
            if len(self._created) > 2000:
                raise HTTPException(503, "Demo capacity reached; retry later")
            session = Session(token=token_urlsafe(32), expires=now + SESSION_TTL, ip=ip)
            self._rebuild(session)
            stamps.append(now)
            self.sessions[session.token] = session
            return self._snapshot(session, True)

    def snapshot(self, token):
        with self._lock:
            return self._snapshot(self._get(token))

    def delete(self, token):
        with self._lock:
            session = self._get(token)
            self._erase(session)
            del self.sessions[token]
            return {"disconnected": True, "key_cleared": True}

    def scenario(self, token, patch, revision):
        with self._lock:
            session = self._get(token)
            self._check_revision(session, revision)
            merged = {**session.scenario, **patch}
            if merged != session.scenario:
                old = session.scenario
                session.scenario = merged
                try:
                    self._rebuild(session)
                except Exception:
                    session.scenario = old
                    raise HTTPException(503, "Scenario calculation unavailable; previous input retained") from None
                session.revision += 1
                session.cancel.set()  # suppress further paid requests for stale inputs
            return self._snapshot(session)

    def configure(self, token, config):
        with self._lock:
            session = self._get(token)
            if session.active_job:
                raise HTTPException(409, "Wait for the current plan to finish before changing model configuration")
            session.key, session.model = config.api_key, config.model
            session.source = "session"
            session.key_expires = min(session.expires, time() + KEY_TTL)
            session.cancel = Event()
            return {"model": self._model_meta(session)}

    def authorize_team(self, token, request):
        with self._lock:
            session = self._get(token)
            if not self._server_available():
                raise HTTPException(409, "Team Claude is not configured by the service owner")
            if session.active_job:
                raise HTTPException(409, "Wait for the current plan to finish before changing model configuration")
            now = time()
            failures = self._team_attempts[session.ip]
            if sum(stamp > now - 60 for stamp in failures) >= 5 or len(failures) >= 20:
                raise HTTPException(429, "Team access attempt limit reached; try again later", headers={"Retry-After": "60"})
            entered = request.access_code.get_secret_value().encode("utf-8")
            expected = self._team_code.get_secret_value().encode("utf-8")
            if not hmac.compare_digest(entered, expected):
                failures.append(now)
                raise HTTPException(403, "Team access code was not accepted")
            session.key = None  # The shared provider key is never copied into a session.
            session.model = self._server_model
            session.source = "render_environment"
            session.key_expires = min(session.expires, now + KEY_TTL)
            session.cancel = Event()
            return {"model": self._model_meta(session)}

    def clear_config(self, token):
        with self._lock:
            session = self._get(token)
            self._erase(session)
            return {"model": self._model_meta(session)}

    def assistant_access(self, token):
        """Authorize the yard assistant without exposing any provider credential."""
        with self._lock:
            session = self._get(token)
            if not self._model_meta(session)["configured"]:
                raise HTTPException(409, "Connect Claude before generating a yard advisory")

    def reserve_assistant(self, token, job_id):
        """Share the existing session, spending and concurrency limits with yard drafts."""
        with self._lock:
            session = self._get(token)
            self.assistant_access(token)
            if session.active_job:
                raise HTTPException(409, "An assistant request is already running for this session")
            now = time()
            while session.calls and session.calls[0] < now - 60:
                session.calls.popleft()
            if len(session.calls) >= 4 or session.model_jobs >= 12 or len(self._model_ips[session.ip]) >= 24:
                raise HTTPException(429, "Claude request limit reached; wait or reconnect later")
            if not self._model_slots.acquire(blocking=False):
                raise HTTPException(429, "Model concurrency limit reached; retry later")
            session.active_job = job_id
            session.cancel = Event()
            session.calls.append(now)
            session.model_jobs += 1
            self._model_ips[session.ip].append(now)
            key = self._server_key if session.source == "render_environment" else session.key
            return {"api_key": key.get_secret_value(), "model": session.model, "_cancel": session.cancel,
                    **({"workspace_id": self._server_workspace} if session.source == "render_environment" and self._server_workspace else {})}

    def finish_assistant(self, token, job_id, cfg):
        cfg.clear()
        with self._lock:
            session = self.sessions.get(token)
            if session and session.active_job == job_id:
                session.active_job = None
        self._model_slots.release()

    @staticmethod
    def _job_view(session, job):
        result = deepcopy({key: value for key, value in job.items() if not key.startswith("_")})
        result["stale"] = job["input_revision"] != session.revision
        return result

    def plans(self, token, plan_id=None):
        with self._lock:
            session = self._get(token)
            if plan_id:
                if plan_id not in session.jobs:
                    raise HTTPException(404, "Plan not found in this session")
                return self._job_view(session, session.jobs[plan_id])
            return {"plans": [self._job_view(session, job) for job in reversed(list(session.jobs.values()))]}

    def plan(self, token, request, revision, idempotency):
        with self._lock:
            session = self._get(token)
            if not idempotency or not 8 <= len(idempotency) <= 128 or not all(c.isalnum() or c in "-_" for c in idempotency):
                raise HTTPException(400, "A valid Idempotency-Key is required")
            fingerprint = (revision, request.top_n, request.use_model)
            # Check retry BEFORE revision/rate limits. It can only return the
            # original job, never dispatch another paid request.
            if idempotency in session.idempotency:
                old_fingerprint, job_id = session.idempotency[idempotency]
                if old_fingerprint != fingerprint:
                    raise HTTPException(409, "Idempotency-Key was already used for a different request")
                return self._job_view(session, session.jobs[job_id])
            self._check_revision(session, revision)
            if session.active_job:
                raise HTTPException(409, "A plan is already running for this session")
            if len(session.jobs) >= MAX_JOBS:
                raise HTTPException(429, "Session plan history limit reached; start a new session")
            now = time()
            while session.calls and session.calls[0] < now - 60:
                session.calls.popleft()
            if len(session.calls) >= 4:
                raise HTTPException(429, "Plan request limit reached; wait a minute", headers={"Retry-After": "60"})
            reserved = False
            if request.use_model:
                if not self._model_meta(session)["configured"]:
                    raise HTTPException(409, "Authorize team Claude or configure a personal key before requesting model assistance")
                if session.model_jobs >= 12 or len(self._model_ips[session.ip]) >= 24:
                    raise HTTPException(429, "Model plan limit reached; continue in deterministic mode")
                if not self._model_slots.acquire(blocking=False):
                    raise HTTPException(429, "Model concurrency limit reached; retry later", headers={"Retry-After": "20"})
                reserved = True
            plan_id = str(uuid4())
            job = {"id": plan_id, "status": "queued", "input_revision": session.revision,
                   "stale": False, "result": None, "error": None, "created_at": _iso(now),
                   "completed_at": None, "use_model": request.use_model}
            session.jobs[plan_id] = job
            session.idempotency[idempotency] = (fingerprint, plan_id)
            session.calls.append(now)
            session.active_job = plan_id
            session.cancel = Event()
            cfg = None
            if request.use_model:
                selected_key = self._server_key if session.source == "render_environment" else session.key
                cfg = {"base_url": "https://api.anthropic.com/v1/", "api_key": selected_key.get_secret_value(),
                       "model": session.model, "_cancel": session.cancel}
                if session.source == "render_environment" and self._server_workspace:
                    cfg["workspace_id"] = self._server_workspace
                session.model_jobs += 1
                self._model_ips[session.ip].append(now)
            try:
                future = self._executor.submit(self._run_job, token, plan_id, deepcopy(session.scenario), request.top_n, cfg)
            except Exception:
                if reserved:
                    self._model_slots.release()
                session.active_job = None
                job.update(status="failed", error="Planner queue unavailable", completed_at=_iso(time()))
                if cfg:
                    cfg.clear()
                return self._job_view(session, job)
            if reserved:
                future.add_done_callback(lambda _future: self._model_slots.release())
            return self._job_view(session, job)

    def _run_job(self, token, plan_id, scenario, top_n, cfg):
        try:
            with self._lock:
                session = self.sessions.get(token)
                if not session:
                    return
                session.jobs[plan_id]["status"] = "running"
            result = run_agent(deepcopy(self.raw), scenario, top_n=top_n, cfg=cfg)
            with self._lock:
                session = self.sessions.get(token)
                if session:
                    session.jobs[plan_id].update(status="succeeded", result=result, completed_at=_iso(time()))
        except Exception:
            # Provider exceptions can contain request headers and credential
            # fragments. Neither logs nor serialized jobs receive their text.
            with self._lock:
                session = self.sessions.get(token)
                if session:
                    session.jobs[plan_id].update(status="failed", error="Planner unavailable; retry in deterministic mode", completed_at=_iso(time()))
        finally:
            if cfg is not None:
                cfg.clear()
            with self._lock:
                session = self.sessions.get(token)
                if session and session.active_job == plan_id:
                    session.active_job = None

    def decide(self, token, plan_id, request, revision):
        with self._lock:
            session = self._get(token)
            self._check_revision(session, revision)
            if plan_id not in session.jobs:
                raise HTTPException(404, "Plan not found in this session")
            job = session.jobs[plan_id]
            if job["input_revision"] != session.revision:
                raise HTTPException(409, "Plan is stale; generate a new plan")
            if job["status"] != "succeeded":
                raise HTTPException(409, "Plan is not ready for a human decision")
            item = next((item for item in job["result"]["actions"]
                         if item["container_id"] == request.container_id and item["blocker"] == request.blocker), None)
            if item is None:
                raise HTTPException(404, "Action is not a member of this saved plan")
            existing = item.get("approval", {"status": "pending"})
            if existing.get("status") != "pending":
                if existing.get("status") == request.decision and existing.get("note") == request.note:
                    return self._job_view(session, job)
                raise HTTPException(409, "This action already has a human decision; generate a new plan to reconsider")
            item["approval"] = {"status": request.decision, "by": "session operator", "at": _iso(time()),
                                "note": request.note, "dispatch": "manual_follow_up_only" if request.decision == "approved" else "none"}
            return self._job_view(session, job)


def install_console(app: FastAPI, settings: Settings) -> ConsoleStore:
    store = ConsoleStore(settings)
    app.state.console_store = store
    router = APIRouter(prefix="/api/console", tags=["Team console"], route_class=BoundedRoute)

    @app.exception_handler(RequestValidationError)
    async def safe_validation(request, exc):
        if request.url.path.startswith("/api/console"):
            return JSONResponse(status_code=422, content={"detail": "Invalid console request; check fields and limits"})
        if request.url.path.startswith("/api/yard"):
            return JSONResponse(status_code=422, content={"detail": "Invalid yard request; check fields and limits"})
        return await request_validation_exception_handler(request, exc)

    @router.get("/ports")
    def ports():
        return {"ports": [{key: profile[key] for key in ("code", "name", "currency", "symbol", "language", "customs_agency")}
                          for profile in PROFILES.values()], "data_kind": "synthetic", "tariff_notice": TARIFF_NOTICE}

    @router.post("/session", status_code=201)
    def create(request: Request):
        # Use the actual ASGI peer. Forwarded-for is never trusted from clients.
        return store.create(request.client.host if request.client else "unknown")

    @router.get("/session")
    def snapshot(x_console_token: str | None = Header(default=None)):
        return store.snapshot(x_console_token)

    @router.delete("/session")
    def delete(x_console_token: str | None = Header(default=None)):
        return store.delete(x_console_token)

    @router.post("/scenario")
    def scenario(patch: ScenarioPatch, x_console_token: str | None = Header(default=None), if_match: str | None = Header(default=None)):
        return store.scenario(x_console_token, patch.model_dump(exclude_unset=True), if_match)

    @router.put("/agent/config")
    def config(body: ConfigInput, x_console_token: str | None = Header(default=None)):
        return store.configure(x_console_token, body)

    @router.delete("/agent/config")
    def clear_config(x_console_token: str | None = Header(default=None)):
        return store.clear_config(x_console_token)

    @router.put("/agent/team")
    def team(body: TeamInput, x_console_token: str | None = Header(default=None)):
        return store.authorize_team(x_console_token, body)

    @router.post("/plans", status_code=202)
    def plan(body: PlanInput, x_console_token: str | None = Header(default=None), if_match: str | None = Header(default=None),
             idempotency_key: str | None = Header(default=None)):
        return store.plan(x_console_token, body, if_match, idempotency_key)

    @router.get("/plans")
    def plans(x_console_token: str | None = Header(default=None)):
        return store.plans(x_console_token)

    @router.get("/plans/{plan_id}")
    def get_plan(plan_id: str, x_console_token: str | None = Header(default=None)):
        return store.plans(x_console_token, plan_id)

    @router.post("/plans/{plan_id}/decisions")
    def decide(plan_id: str, body: DecisionInput, x_console_token: str | None = Header(default=None), if_match: str | None = Header(default=None)):
        return store.decide(x_console_token, plan_id, body, if_match)

    app.include_router(router)
    return store
