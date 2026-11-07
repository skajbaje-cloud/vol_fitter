"""Browse what's in the database: names, their snapshots, and each snapshot's expiries."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends

from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.web.deps import get_repo, require_name
from vol_fitter.web.schemas import NameOut

router = APIRouter(prefix="/api/names", tags=["names"])


@router.get("", response_model=list[NameOut])
def list_names(repo: VolFitterRepository = Depends(get_repo)) -> list[NameOut]:
    return [
        NameOut(name_id=r.name_id, name=r.name, chain_ric=r.chain_ric, display_name=r.display_name, active=r.active)
        for r in repo.list_names()
    ]


@router.get("/{name}/snapshots", response_model=list[datetime])
def list_snapshots(name: str, repo: VolFitterRepository = Depends(get_repo)) -> list[datetime]:
    record = require_name(repo, name)
    return repo.list_snapshot_timestamps(record.name_id)


@router.get("/{name}/snapshots/{snapshot_ts}/maturities", response_model=list[date])
def list_maturities(name: str, snapshot_ts: datetime, repo: VolFitterRepository = Depends(get_repo)) -> list[date]:
    record = require_name(repo, name)
    return repo.list_maturities(record.name_id, snapshot_ts)
