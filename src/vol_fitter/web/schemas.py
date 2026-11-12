"""Pydantic request/response models -- the HTTP contract the frontend codes against."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from vol_fitter.web.schemas_fits import FitSnapshotSummaryOut
from vol_fitter.web.schemas_names import ChainCheckOut, NameLookupOut, NameOut  # noqa: F401  (re-exported)


class SmileQuotes(BaseModel):
    """Columnar arrays, one entry per listed option at this expiry."""
    strike: list[float]
    is_call: list[bool]
    bid: list[float | None]
    ask: list[float | None]
    bid_iv: list[float | None]
    ask_iv: list[float | None]
    bid_delta: list[float | None]
    ask_delta: list[float | None]
    fwd_delta: list[float | None]    # forward call-equivalent delta the smile model is evaluated at


class MaturityParamsOut(BaseModel):
    forward: float | None
    discount_factor: float | None
    n_strikes_forward: int | None
    n_strikes_df: int | None
    forward_fit_resid: float | None
    df_fit_resid: float | None
    sigma_atm: float | None
    skew: float | None
    kappa_call: float | None
    kappa_put: float | None
    smile_fit_rmse: float | None
    smile_quality_flag: str | None
    fit_status: str | None = None
    pct_inside: float | None = None
    n_fit_quotes: int | None = None
    n_outliers: int | None = None


class SmileOut(BaseModel):
    name: str
    snapshot_ts: datetime
    expiry: date
    T: float | None
    spot: float | None
    h_min: float                     # bid-ask fitter's half-spread floor, for "inside" checks client-side
    params: MaturityParamsOut
    quotes: SmileQuotes


class SnapshotRunRequest(BaseModel):
    names: list[str] = Field(min_length=1, max_length=500)   # registered names, snapped in this order


class JobOut(BaseModel):
    id: int
    kind: str
    name: str
    status: str
    submitted_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    origin: str = "manual"
    snapshot_ts: datetime | None = None
    spot: float | None = None
    window_vol: float | None = None
    window_size: int | None = None
    n_quotes: int | None = None
    n_maturities: int | None = None
    duration_sec: float | None = None
    lookup: list[NameLookupOut] | None = None    # kind == "lookup"
    check: ChainCheckOut | None = None           # kind == "check"
    fit: list[FitSnapshotSummaryOut] | None = None   # kind == "fit": one entry per snapshot fitted
