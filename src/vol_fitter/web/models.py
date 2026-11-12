"""Plain data holders for the web layer's background jobs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

JOB_KINDS = ("snapshot", "lookup", "check", "fit")


@dataclass
class Job:
    id: int
    kind: str                       # one of JOB_KINDS
    name: str                       # label shown in the runs table (a RIC, or a list of RICs for a lookup)
    submitted_at: datetime
    status: str = "queued"          # queued -> running -> done | failed
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result: Any = None              # SnapshotRunResult | list[NameLookupResult] | ChainCheck | list[FitRunResult]
    payload: dict = field(default_factory=dict, repr=False)
    origin: str = "manual"          # manual | schedule
