"""Bid-ask spline study: every expiry of one snapshot, read-only (nothing is stored)."""
from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime

import numpy as np
from fastapi import APIRouter, Depends

from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.orchestration.spline_run import ExpirySpline, run_spline_study
from vol_fitter.web.deps import get_repo, require_name
from vol_fitter.web.schemas_spline import SmileModelOut, SplineExpiryOut, SplinePointsOut, WingPeakOut

router = APIRouter(prefix="/api/spline", tags=["spline"])


def _floats(a, digits: int = 7) -> list:
    """Arrays -> JSON lists, NaN as null, rounded to keep the payload small."""
    return [None if not math.isfinite(v) else round(float(v), digits) for v in np.asarray(a, dtype=float)]


def _out(e: ExpirySpline) -> SplineExpiryOut:
    f, p = e.fit, e.fit.points
    slack = np.concatenate([f.bid_slack, f.ask_slack])
    return SplineExpiryOut(
        expiry=e.expiry, T=e.T, forward=e.forward, status=f.status, message=f.message,
        n_bounds=int(np.isfinite(p.iv_bid).sum() + np.isfinite(p.iv_ask).sum()),
        n_active=int(f.bid_active.sum() + f.ask_active.sum()), n_broken=int((slack > 0).sum()),
        max_break=float(slack.max()) if slack.size else 0.0,
        roughness=None if not math.isfinite(f.roughness) else f.roughness, monotone_ok=f.monotone_ok,
        s2_atm=f.s2_atm, put_peak=WingPeakOut(**asdict(f.put_peak)), call_peak=WingPeakOut(**asdict(f.call_peak)),
        model=SmileModelOut(**e.model) if e.model else None,
        grid_z=_floats(f.grid_z, 4), s=_floats(f.s), s1=_floats(f.s1), s2=_floats(f.s2),
        points=SplinePointsOut(
            strike=_floats(p.strike, 4), is_call=p.is_call.tolist(),
            z_bid=_floats(p.z_bid, 5), iv_bid=_floats(p.iv_bid), z_ask=_floats(p.z_ask, 5), iv_ask=_floats(p.iv_ask),
            bid_active=f.bid_active.tolist(), ask_active=f.ask_active.tolist(),
            bid_slack=_floats(f.bid_slack), ask_slack=_floats(f.ask_slack),
        ),
    )


@router.get("/{name}/{snapshot_ts}", response_model=list[SplineExpiryOut])
def spline_study(name: str, snapshot_ts: datetime, repo: VolFitterRepository = Depends(get_repo)) -> list[SplineExpiryOut]:
    record = require_name(repo, name)
    return [_out(e) for e in run_spline_study(repo, record.name_id, snapshot_ts)]
