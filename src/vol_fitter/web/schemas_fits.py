"""HTTP contract for smile fits: run them, see coverage per snapshot, and per-expiry results."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FitMode = Literal["latest", "unfitted", "snapshot"]


class FitRunRequest(BaseModel):
    names: list[str] = Field(min_length=1, max_length=500)
    mode: FitMode = "latest"                 # latest snapshot | every unfitted snapshot | one given snapshot
    snapshot_ts: datetime | None = None      # only with mode "snapshot" (and a single name)
    anchor: bool = True                      # warm-start/anchor each expiry on the previous fit

    @model_validator(mode="after")
    def _snapshot_needs_ts(self) -> "FitRunRequest":
        if self.mode == "snapshot" and (self.snapshot_ts is None or len(self.names) != 1):
            raise ValueError("mode 'snapshot' takes exactly one name and a snapshot_ts")
        return self


class FitCoverageOut(BaseModel):
    name: str
    snapshot_ts: datetime
    n_expiries: int
    n_fitted: int
    n_ok: int
    mean_pct_inside: float | None
    min_pct_inside: float | None
    n_outliers: int | None
    last_fit_ts: datetime | None


class ExpiryFitOut(BaseModel):
    expiry_date: date
    T: float | None
    forward: float | None
    fit_status: str | None
    smile_quality_flag: str | None
    pct_inside: float | None
    smile_fit_rmse: float | None
    n_fit_quotes: int | None
    n_outliers: int | None
    sigma_atm: float | None
    skew: float | None
    kappa_put: float | None
    kappa_call: float | None
    refit: bool | None
    anchor_snapshot_ts: datetime | None
    fit_ts: datetime | None


class FitSnapshotSummaryOut(BaseModel):
    """One fitted snapshot inside a fit job's result."""
    snapshot_ts: datetime
    n_expiries: int
    n_ok: int
    mean_pct_inside: float | None
    min_pct_inside: float | None
    n_outliers: int
    n_model_miss: int
    duration_sec: float
