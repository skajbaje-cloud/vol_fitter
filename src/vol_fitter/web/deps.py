"""Shared FastAPI dependencies (overridable in tests via app.dependency_overrides)."""
from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException, Request

from vol_fitter.db.engine import build_engine
from vol_fitter.db.models import NameRecord
from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.web.jobs import JobQueue


@lru_cache(maxsize=1)
def _default_repo() -> VolFitterRepository:
    return VolFitterRepository(build_engine())


def get_repo() -> VolFitterRepository:
    return _default_repo()


def get_job_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue


def require_name(repo: VolFitterRepository, name: str) -> NameRecord:
    record = repo.get_name(name)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown underlying '{name}'.")
    return record
