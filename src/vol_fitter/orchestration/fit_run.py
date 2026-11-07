"""Fit the per-expiry delta smile for one stored snapshot and persist it.

Each expiry is fitted on its own with bidask_fit. The latest earlier successful
fit of the same expiry (within ANCHOR_MAX_AGE_DAYS) is the warm start, and --
when config.ANCHOR_LAMBDA > 0 -- also the parameter-space anchor.
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np
import pandas as pd

from vol_fitter import config
from vol_fitter.bidask_fit import BidAskFitter, FitConfig, FitResult, QuoteClass
from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.logging_setup import get_logger
from vol_fitter.orchestration.models import ExpiryFitSummary, FitRunResult
from vol_fitter.orchestration.snapshot_run import UnregisteredNameError
from vol_fitter.smile import DeltaSmileModel, FitFrameBuilder, SmileParams

logger = get_logger(__name__)


def default_fit_config(lam_a: float = config.ANCHOR_LAMBDA) -> FitConfig:
    return FitConfig(lam_a=lam_a, anchor_scale=config.ANCHOR_SCALE, taper_col="otm_delta")


def run_fit(
    repo: VolFitterRepository,
    underlying: str,
    snapshot_ts: datetime | None = None,
    anchor: bool = True,
    cfg: FitConfig | None = None,
    model: DeltaSmileModel | None = None,
) -> FitRunResult:
    t0 = time.time()
    rec = repo.get_name(underlying)
    if rec is None:
        raise UnregisteredNameError(f"'{underlying}' isn't registered")
    if snapshot_ts is None:
        stamps = repo.list_snapshot_timestamps(rec.name_id)
        if not stamps:
            raise ValueError(f"no snapshots stored for {underlying}")
        snapshot_ts = stamps[0]
    cfg = cfg or default_fit_config()
    model = model or DeltaSmileModel()
    fitter = BidAskFitter(cfg)

    frame = FitFrameBuilder().build(repo.fetch_quotes(rec.name_id, snapshot_ts),
                                    repo.fetch_maturity_params(rec.name_id, snapshot_ts))
    prev = repo.fetch_previous_fits(rec.name_id, snapshot_ts, config.ANCHOR_MAX_AGE_DAYS) if anchor else pd.DataFrame()
    prev_by_expiry = {r.expiry_date: r for r in prev.itertuples()} if len(prev) else {}

    fit_ts = datetime.now().replace(microsecond=0)
    mat_rows, quote_frames, summaries = [], [], []
    for expiry, grp in frame.groupby("expiry", sort=True):
        grp = grp.reset_index(drop=True)
        prev_row = prev_by_expiry.get(expiry)
        p_prev = None if prev_row is None else np.array([getattr(prev_row, n) for n in SmileParams.NAMES], float)
        p0 = p_prev if p_prev is not None else model.initial_guess(grp)
        res = fitter.fit(model, grp, p0, model.bounds(), p_prev=p_prev, model_penalty=model.positivity_penalty)

        anchor_ts = None if prev_row is None else pd.Timestamp(prev_row.snapshot_ts).to_pydatetime()
        summary = _summary(expiry, res, anchor_ts)
        summaries.append(summary)
        mat_rows.append(_maturity_row(rec.name_id, snapshot_ts, expiry, grp, res, summary, model, fit_ts))
        quote_frames.append(_quote_rows(rec.name_id, snapshot_ts, grp, res))
        logger.info("%s %s: %s, %.0f%% inside of %d, p=%s%s", underlying, expiry, res.status.value,
                    100 * res.pct_inside, res.n_quotes, np.round(res.p, 4),
                    " (anchored)" if anchor_ts else "")

    if mat_rows:
        repo.upsert_maturity_params(pd.DataFrame(mat_rows))
        repo.upsert_fit_quotes(pd.concat(quote_frames, ignore_index=True))
    return FitRunResult(name=underlying, snapshot_ts=snapshot_ts, expiries=summaries,
                        n_quotes=len(frame), duration_sec=time.time() - t0)


def run_unfitted(repo: VolFitterRepository, underlying: str, anchor: bool = True) -> list[FitRunResult]:
    """Fit every not-yet-fitted snapshot oldest first, so each can anchor to the one before."""
    rec = repo.get_name(underlying)
    if rec is None:
        raise UnregisteredNameError(f"'{underlying}' isn't registered")
    return [run_fit(repo, underlying, ts, anchor=anchor) for ts in repo.list_unfitted_snapshots(rec.name_id)]


def _summary(expiry, res: FitResult, anchor_ts) -> ExpiryFitSummary:
    cls = res.quotes["classification"]
    return ExpiryFitSummary(
        expiry_date=expiry, status=res.status.value, params=tuple(float(v) for v in res.p),
        n_quotes=res.n_quotes, pct_inside=res.pct_inside,
        n_outliers=int((cls == QuoteClass.OUTLIER.value).sum()),
        n_model_miss=int((cls == QuoteClass.MODEL_MISS.value).sum()),
        anchor_snapshot_ts=anchor_ts, anchor_lambda=res.anchor_lambda, flags=list(res.flags),
    )


def _maturity_row(name_id, snapshot_ts, expiry, grp, res: FitResult, s: ExpiryFitSummary, model, fit_ts) -> dict:
    two = grp["bid_iv"].notna() & grp["ask_iv"].notna() & ~res.quotes["excluded"]
    mid = 0.5 * (grp["bid_iv"] + grp["ask_iv"])
    rmse = float(np.sqrt(np.mean((res.quotes.loc[two, "model_iv"] - mid[two]) ** 2))) if two.any() else None
    flag = "failed" if s.status != "ok" else ("miss" if s.n_model_miss else "ok")
    p = SmileParams.from_vector(res.p)
    return {
        "name_id": name_id, "snapshot_ts": snapshot_ts, "expiry_date": expiry,
        "sigma_atm": p.sigma_atm, "skew": p.skew, "kappa_put": p.kappa_put, "kappa_call": p.kappa_call,
        "smile_fit_rmse": rmse, "smile_quality_flag": flag, "fit_status": s.status,
        "fit_objective": res.objective, "n_fit_quotes": res.n_quotes, "pct_inside": res.pct_inside,
        "n_outliers": s.n_outliers, "refit": res.p_first is not None,
        "anchor_snapshot_ts": s.anchor_snapshot_ts, "anchor_lambda": res.anchor_lambda,
        "fit_ts": fit_ts,
    }


def _quote_rows(name_id, snapshot_ts, grp, res: FitResult) -> pd.DataFrame:
    q = res.quotes
    return pd.DataFrame({
        "name_id": name_id, "snapshot_ts": snapshot_ts,
        "instrument": grp["instrument"].to_numpy(), "expiry_date": grp["expiry"].to_numpy(),
        "delta": grp["delta"].to_numpy(), "model_iv": q["model_iv"].to_numpy(), "u": q["u"].to_numpy(),
        "v_ask": q["v_ask"].to_numpy(), "v_bid": q["v_bid"].to_numpy(),
        "x_capped": q["x_capped"].to_numpy(), "inside": q["inside"].to_numpy(),
        "classification": q["classification"].to_numpy(), "excluded": q["excluded"].to_numpy(),
    })
