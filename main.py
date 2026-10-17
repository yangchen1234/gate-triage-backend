"""Run with uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1."""

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gate_triage.config import Settings
from gate_triage.models import ApprovalDecision, ScenarioPatch
from gate_triage.service import QueueService, ReasonFunction, ScoreFunction


logger = logging.getLogger(__name__)
WEB_DIST = Path(__file__).resolve().parent / "apps" / "web" / "dist"


def create_app(settings: Settings | None = None, *, scorer: ScoreFunction | None = None,
               reasoner: ReasonFunction | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    console_store = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = QueueService(config, scorer=scorer, reasoner=reasoner)
        app.state.service = service
        task = None
        if service.has_reasoner:
            task = asyncio.create_task(asyncio.to_thread(service.enrich_reasons, 1))
        try:
            yield
        finally:
            if console_store is not None:
                console_store.close()
            if task:
                await task

    app = FastAPI(
        title="Gate Triage API", version="0.2.0", lifespan=lifespan,
        description="Advisory port container triage and FIFO-vs-priority fee simulation. Demo data is synthetic.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=list(config.cors_origins),
                       allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["*"])

    @app.middleware("http")
    async def browser_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/console"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self' data:; font-src 'self'; "
                "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
            )
        elif request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.get("/containers", summary="Current queue in descending priority order")
    def containers() -> list[dict]:
        return app.state.service.snapshot().queue

    @app.get("/containers/{container_id}", summary="Container source details and reason")
    def container(container_id: str) -> dict:
        for row in app.state.service.snapshot().queue:
            if row["container_id"] == container_id:
                return row
        raise HTTPException(status_code=404, detail="Container not found")

    @app.post("/scenario", summary="Merge scenario fields and re-rank the queue")
    def scenario(patch: ScenarioPatch, background_tasks: BackgroundTasks) -> list[dict]:
        service = app.state.service
        try:
            updated = service.update(patch.model_dump(exclude_unset=True))
        except Exception:
            logger.warning("Scenario scoring failed; preserving the previous snapshot")
            raise HTTPException(status_code=503, detail="Scoring failed; previous scenario and queue retained") from None
        if service.has_reasoner:
            background_tasks.add_task(service.enrich_reasons, updated.generation)
        return updated.queue

    @app.get("/plan", summary="Agent: today's action list — blockers worth resolving, with drafted outreach and trace")
    def plan(top_n: int = 5) -> dict:
        from gate_triage.agent import run_agent
        service = app.state.service
        snapshot = service.snapshot()
        try:
            # Public legacy reads never spend deployment credentials. Paid generation
            # is explicit and authenticated through the isolated console session.
            result = run_agent(service._raw, snapshot.scenario, top_n=max(1, min(top_n, 10)), cfg=None)
        except Exception:
            logger.warning("Legacy planner failed; provider details withheld")
            raise HTTPException(status_code=503, detail="Planner agent unavailable") from None
        # Overlay planner decisions so a refresh keeps approved/rejected state ｜ 叠加人工批准状态
        approvals = getattr(app.state, "approvals", {})
        for item in result["actions"]:
            key = f"{item['container_id']}:{item['blocker']}"
            if key in approvals:
                item["approval"] = approvals[key]
        return result

    @app.post("/plan/approve", summary="Planner approves or rejects one action. Nothing is ever sent automatically.")
    def approve(decision: ApprovalDecision) -> dict:
        from datetime import datetime, timezone
        if not hasattr(app.state, "approvals"):
            app.state.approvals = {}
        record = {
            "status": decision.decision,                       # approved | rejected
            "by": decision.planner or "planner",
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": decision.note,
            "dispatch": "queued_for_human_send" if decision.decision == "approved" else "none",
        }
        app.state.approvals[f"{decision.container_id}:{decision.blocker}"] = record
        return {"container_id": decision.container_id, "blocker": decision.blocker, "approval": record}

    @app.get("/plan/approvals", summary="All planner decisions so far")
    def approvals() -> dict:
        return getattr(app.state, "approvals", {})

    @app.get("/stats", summary="Action counts and one-day fee simulation")
    def stats() -> dict:
        return app.state.service.snapshot().stats

    @app.get("/health", summary="Service status and actual explanation mode")
    def health() -> dict:
        snapshot = app.state.service.snapshot()
        return {
            "status": "ok", "llm": snapshot.llm, "llm_status": snapshot.llm_status,
            "llm_configured": app.state.service.has_reasoner,
            "container_count": len(snapshot.queue), "generation": snapshot.generation,
            "scoring_ms": snapshot.scoring_ms, "scenario": snapshot.scenario,
            "scorer": config.scorer,
        }

    from gate_triage.console import install_console
    console_store = install_console(app, config)

    if (WEB_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="web-assets")

    @app.get("/", include_in_schema=False)
    def web_console():
        index = WEB_DIST / "index.html"
        if not index.is_file():
            raise HTTPException(503, "Build the web console: cd apps/web && pnpm install && pnpm build")
        return FileResponse(index)

    return app


app = create_app()
