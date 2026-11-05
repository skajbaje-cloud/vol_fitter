"""Plain data holders for the snapshot library.

The universe and the windowed quote set are bulk, DataFrame-shaped data
(thousands of rows); Quote/UniverseEntry exist for single-row convenience
and tests. SnapshotMeta is genuinely one row per snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class UniverseEntry:
    instrument: str
    strike: float
    expiry_date: date
    is_call: bool


@dataclass(frozen=True)
class Quote:
    instrument: str
    strike: float
    expiry_date: date
    T: float
    is_call: bool
    bid: float
    ask: float


@dataclass(frozen=True)
class SnapshotMeta:
    name: str
    snapshot_ts: datetime
    spot: float
    universe_size: int
    window_size: int
    snap_duration_sec: float
    status: str = "ok"
