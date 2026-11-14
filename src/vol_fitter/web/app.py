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
from vol_fitter.orchestration.fit_run import run_fit_job
from vol_fitter.orchestration.lookup_run import run_chain_check, run_lookup
from vol_fitter.orchestration.snapshot_run import run_snapshot
from vol_fitter.scheduling.scheduler import Scheduler
from vol_fitter.web import routes_fits, routes_jobs, routes_names, routes_schedule, routes_smile, routes_spline
from vol_fitter.web.deps import get_repo
from vol_fitter.web.jobs import JobQueue, JobRunner

logger = get_logger(__name__)

DEFAULT_RUNNERS: dict[str, JobRunner] = {
    "snapshot": lambda p: run_snapshot(get_repo(), p["name"], p.get("chain_ric")),
    "lookup": lambda p: run_lookup(p["rics"]),
    "check": lambda p: run_chain_check(p["name"], p["chain_ric"]),
    "fit": lambda p: run_fit_job(get_repo(), p["name"], p["mode"], p.get("snapshot_ts"), p.get("anchor", True)),
}


def create_app(runners: dict[str, JobRunner] | None = None, frontend_dist: Path | None = None,
               start_scheduler: bool = False) -> FastAPI:
    """start_scheduler runs the snapshot scheduler thread; off by default so tests never fire real jobs."""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        all_runners = {**DEFAULT_RUNNERS, **(runners or {})}
        app.state.job_queue = JobQueue({k: v for k, v in all_runners.items() if k != "fit"})
        app.state.fit_queue = JobQueue({"fit": all_runners["fit"]}, worker_name="fit-worker")
        app.state.scheduler = Scheduler(get_repo, app.state.job_queue) if start_scheduler else None
        if app.state.scheduler:
            app.state.scheduler.start()
        yield
        if app.state.scheduler:
            app.state.scheduler.stop()
        app.state.job_queue.stop()
        app.state.fit_queue.stop()

    app = FastAPI(title="vol_fitter", lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(routes_names.router)
    app.include_router(routes_smile.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_fits.router)
    app.include_router(routes_schedule.router)
    app.include_router(routes_spline.router)

    dist = frontend_dist or config.FRONTEND_DIST
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        logger.warning("frontend build not found at %s -- serving the API only (run `npm run build` in frontend/)", dist)
    return app


app = create_app(start_scheduler=config.SCHEDULER_ENABLED)
