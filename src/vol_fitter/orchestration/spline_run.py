"""Bid-ask spline study for one snapshot: every expiry's curve and curvature (read-only, nothing stored).

A snapshot's quotes never change, so results are cached per (name, snapshot).
"""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.logging_setup import get_logger
from vol_fitter.smile.bidask_spline import BidAskSpline
from vol_fitter.smile.models import SplineConfig, SplineFit
from vol_fitter.smile.spline_points import SplinePointBuilder

logger = get_logger(__name__)

_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_CACHE_SIZE = 32
_MODEL_COLS = ("sigma_atm", "skew", "kappa_put", "kappa_call")


@dataclass(frozen=True)
class ExpirySpline:
    expiry: date
    T: float
    forward: float
    fit: SplineFit
    model: dict | None          # the stored per-expiry smile params, when that expiry was fitted


def run_spline_study(repo: VolFitterRepository, name_id: int, snapshot_ts: datetime,
                     cfg: SplineConfig = SplineConfig()) -> list[ExpirySpline]:
    # Quotes never change, so the spline fits are cached; model params (a refit rewrites them) are read fresh.
    mats = repo.fetch_maturity_params(name_id, snapshot_ts).sort_values("expiry_date")
    mats = mats[mats["forward"].notna() & mats["T"].notna() & (mats["T"] > 0)]
    fits = _fits(repo, name_id, snapshot_ts, mats, cfg)
    out = []
    for _, m in mats.iterrows():
        model = {c: float(m[c]) for c in _MODEL_COLS} if all(pd.notna(m.get(c)) for c in _MODEL_COLS) else None
        out.append(ExpirySpline(expiry=m["expiry_date"], T=float(m["T"]), forward=float(m["forward"]),
                                fit=fits[m["expiry_date"]], model=model))
    return out


def _fits(repo, name_id: int, snapshot_ts: datetime, mats: pd.DataFrame, cfg: SplineConfig) -> dict[date, SplineFit]:
    key = (name_id, snapshot_ts, cfg)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    t0 = time.time()
    quotes = repo.fetch_quotes(name_id, snapshot_ts).sort_values(["strike", "is_call"])
    builder, spline = SplinePointBuilder(cfg), BidAskSpline(cfg)
    fits = {}
    for _, m in mats.iterrows():
        q = quotes[quotes["expiry_date"] == m["expiry_date"]]
        fits[m["expiry_date"]] = spline.fit(builder.build(q, float(m["forward"]), float(m["T"])), float(m["T"]))
    logger.info("spline study name_id=%s @ %s: %d expiries in %.1fs", name_id, snapshot_ts, len(fits), time.time() - t0)
    _CACHE[key] = fits
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return fits
