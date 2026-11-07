"""One expiry's smile: every quote's bid/ask IV and delta, plus that expiry's fit params."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.web.deps import get_repo, require_name
from vol_fitter.web.schemas import MaturityParamsOut, SmileOut, SmileQuotes

router = APIRouter(prefix="/api", tags=["smile"])

_QUOTE_FIELDS = ["strike", "is_call", "bid", "ask", "bid_iv", "ask_iv", "bid_delta", "ask_delta"]


def _nullable(values: pd.Series) -> list:
    # JSON has no NaN; MySQL NULLs arrive from pandas as NaN.
    return values.astype(object).where(values.notna(), None).tolist()


@router.get("/smile", response_model=SmileOut)
def get_smile(
    name: str,
    snapshot_ts: datetime,
    expiry: date = Query(...),
    repo: VolFitterRepository = Depends(get_repo),
) -> SmileOut:
    record = require_name(repo, name)
    params = repo.fetch_maturity_params(record.name_id, snapshot_ts, expiry)
    if params.empty:
        raise HTTPException(status_code=404, detail=f"No data for {name} @ {snapshot_ts} expiring {expiry}.")
    quotes = repo.fetch_quotes(record.name_id, snapshot_ts, expiry).sort_values(["strike", "is_call"])
    snapshot = repo.fetch_snapshot(record.name_id, snapshot_ts) or {}

    p = {k: v for k, v in zip(params.columns, _nullable(params.iloc[0]))}
    quotes["is_call"] = quotes["is_call"].astype(bool)
    return SmileOut(
        name=name,
        snapshot_ts=snapshot_ts,
        expiry=expiry,
        T=p.get("T"),
        spot=snapshot.get("spot"),
        params=MaturityParamsOut(**{k: p.get(k) for k in MaturityParamsOut.model_fields}),
        quotes=SmileQuotes(**{f: _nullable(quotes[f]) if f != "is_call" else quotes[f].tolist() for f in _QUOTE_FIELDS}),
    )
