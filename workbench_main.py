"""Independent full-stack demo entry point; legacy main.py is untouched."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gate_triage.workbench.api import install_handlers, router
from gate_triage.workbench.db import configure_database
from gate_triage.workbench.emergency import router as emergency_router
from gate_triage.workbench.knowledge import router as knowledge_router
from gate_triage.workbench.spatial import router as spatial_router
from gate_triage.workbench.scale import router as scale_router
from gate_triage.workbench.worker import start_worker, stop_worker

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "apps/web/dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_database()
    start_worker()
    yield
    stop_worker()


def create_app() -> FastAPI:
    application = FastAPI(title="Gate Triage Workbench", version="1.1.0", lifespan=lifespan)
    install_handlers(application)
    application.include_router(router)
    application.include_router(knowledge_router)
    application.include_router(spatial_router)
    application.include_router(emergency_router)
    application.include_router(scale_router)
    if (DIST / "assets").exists():
        application.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @application.get("/reference/realtime-decision-contract.zh-CN.md", include_in_schema=False)
    def decision_contract():
        return FileResponse(ROOT / "docs/realtime-decision-contract.zh-CN.md", media_type="text/plain; charset=utf-8")

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found")
        index = DIST / "index.html"
        if not index.exists():
            raise HTTPException(503, "Build the web app first: cd apps/web && pnpm build")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return application


app = create_app()
