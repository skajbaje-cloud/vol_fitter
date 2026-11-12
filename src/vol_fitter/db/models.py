"""Plain data holders for the single-row tables (names, snapshots).

The bulk tables (raw_quotes, maturity_params, master_params) are written
and read as pandas DataFrames directly in repository.py — a dataclass per
row would just be overhead for tables with thousands of rows per snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NameRecord:
    name: str
    chain_ric: str | None = None
    display_name: str | None = None
    active: bool = True
    group_name: str | None = None
    expiry_filter: str = "all"  # "all" | "monthly"
    timezone: str | None = None  # IANA zone for scheduled snap times
    name_id: int | None = None  # set when read back from the database, ignored on insert


@dataclass(frozen=True)
class SnapshotRecord:
    name_id: int
    snapshot_ts: datetime
    spot: float | None = None
    universe_size: int | None = None
    window_size: int | None = None
    snap_duration_sec: float | None = None
    status: str = "ok"
