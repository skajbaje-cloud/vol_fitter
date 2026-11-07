"""Plain data holders for the web layer's background jobs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from vol_fitter.orchestration.models import SnapshotRunResult


@dataclass
class Job:
    id: int
    kind: str
    name: str
    submitted_at: datetime
    status: str = "queued"          # queued -> running -> done | failed
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result: SnapshotRunResult | None = None
    chain_ric: str | None = field(default=None, repr=False)
