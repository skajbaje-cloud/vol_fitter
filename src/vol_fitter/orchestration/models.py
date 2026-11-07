"""Plain data holders for end-to-end runs that span snapshot, pricing and db."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
