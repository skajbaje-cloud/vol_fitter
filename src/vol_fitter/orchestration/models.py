"""Plain data holders for end-to-end runs that span snapshot, pricing and db."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class ExpiryFitSummary:
    expiry_date: date
    status: str
    params: tuple[float, ...]            # sigma_atm, skew, kappa_put, kappa_call
    n_quotes: int
    pct_inside: float
    n_outliers: int
    n_model_miss: int
    anchor_snapshot_ts: datetime | None  # previous fit used as warm start / anchor
    anchor_lambda: float
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FitRunResult:
    name: str
    snapshot_ts: datetime
    expiries: list[ExpiryFitSummary]
    n_quotes: int
    duration_sec: float


@dataclass(frozen=True)
class SnapshotRunResult:
    name: str
    snapshot_ts: datetime
    spot: float
    window_vol: float | None
    universe_size: int
    window_size: int
    n_quotes: int
    n_maturities: int
    duration_sec: float
