"""Pydantic request/response models -- the HTTP contract the frontend codes against."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class NameOut(BaseModel):
    name_id: int
    name: str
    chain_ric: str | None
    display_name: str | None
    active: bool


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


class SmileOut(BaseModel):
    name: str
    snapshot_ts: datetime
    expiry: date
    T: float | None
    spot: float | None
    params: MaturityParamsOut
    quotes: SmileQuotes


class SnapshotRunRequest(BaseModel):
    scope: Literal["single", "universe"] = "single"
    underlying: str | None = None
    chain_ric: str | None = None


class JobOut(BaseModel):
    id: int
    kind: str
    name: str
    status: str
    submitted_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    snapshot_ts: datetime | None = None
    spot: float | None = None
    window_vol: float | None = None
    window_size: int | None = None
    n_quotes: int | None = None
    n_maturities: int | None = None
    duration_sec: float | None = None
