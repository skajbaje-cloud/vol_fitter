"""FastAPI app: the /api routes plus the built frontend, served from one port.

One process, one port is deliberate -- `cloudflared tunnel --url
http://localhost:8000` then exposes the whole console with no reverse proxy.

Run:  uvicorn vol_fitter.web.app:app --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vol_fitter import config
from vol_fitter.logging_setup import get_logger
from vol_fitter.orchestration.snapshot_run import run_snapshot
from vol_fitter.web import routes_jobs, routes_names, routes_smile
from vol_fitter.web.deps import get_repo
from vol_fitter.web.jobs import JobQueue, SnapshotRunner

logger = get_logger(__name__)


def _default_runner(name: str, chain_ric: str | None):
    return run_snapshot(get_repo(), name, chain_ric)


def create_app(runner: SnapshotRunner = _default_runner, frontend_dist: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.job_queue = JobQueue(runner)
        yield
        app.state.job_queue.stop()

    app = FastAPI(title="vol_fitter", lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(routes_names.router)
    app.include_router(routes_smile.router)
    app.include_router(routes_jobs.router)

    dist = frontend_dist or config.FRONTEND_DIST
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        logger.warning("frontend build not found at %s -- serving the API only (run `npm run build` in frontend/)", dist)
    return app


app = create_app()
