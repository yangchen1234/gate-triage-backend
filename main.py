"""Run with uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1."""

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from gate_triage.config import Settings
from gate_triage.models import ScenarioPatch
from gate_triage.service import QueueService, ReasonFunction, ScoreFunction


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, scorer: ScoreFunction | None = None,
               reasoner: ReasonFunction | None = None) -> FastAPI:
    config = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = QueueService(config, scorer=scorer, reasoner=reasoner)
        app.state.service = service
        task = None
        if service.has_reasoner:
            task = asyncio.create_task(asyncio.to_thread(service.enrich_reasons, 1))
        yield
        if task:
            await task

    app = FastAPI(
        title="Gate Triage API", version="0.1.0", lifespan=lifespan,
        description="Advisory port container triage and FIFO-vs-priority fee simulation. Demo data is synthetic.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=list(config.cors_origins),
                       allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])

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

    @app.get("/plan", summary="Agent: today's action list — blockers worth resolving, with drafted outreach")
    def plan(top_n: int = 5) -> dict:
        from gate_triage.agent import run_agent
        service = app.state.service
        snapshot = service.snapshot()
        try:
            return run_agent(service._raw, snapshot.scenario, top_n=max(1, min(top_n, 10)))
        except Exception as exc:
            logger.warning("Agent failed: %s", exc)
            raise HTTPException(status_code=503, detail="Planner agent unavailable") from None

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

    return app


app = create_app()
