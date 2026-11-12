"""Plain data holders for the snapshot library.

The universe and the windowed quote set are bulk, DataFrame-shaped data
(thousands of rows); Quote/UniverseEntry exist for single-row convenience
and tests. SnapshotMeta is genuinely one row per snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    window_vol: float | None = None  # the realized vol used to size the std-dev window


@dataclass(frozen=True)
class ChainCandidate:
    chain_ric: str
    title: str
    preferred: bool = False   # best guess at the underlying's main listed-option chain


@dataclass(frozen=True)
class NameLookupResult:
    """What LSEG knows about a typed RIC, before anything is written to the database."""
    ric: str
    found: bool
    display_name: str | None = None
    spot: float | None = None
    currency: str | None = None
    vol: float | None = None                      # TR.Volatility40D as a fraction
    candidates: list[ChainCandidate] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class ChainCheck:
    """Contents of a chain after full expansion (slow for big chains; warms the universe cache)."""
    name: str
    chain_ric: str
    n_options: int
    n_expiries: int
    first_expiry: date | None
    last_expiry: date | None
    strike_min: float | None
    strike_max: float | None
    underlying_match: float | None   # share of options whose UNDERLYING is this name (None if not reported)
    duration_sec: float
