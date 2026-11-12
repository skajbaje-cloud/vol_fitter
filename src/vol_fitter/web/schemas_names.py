"""HTTP contract for managing names: register, edit, LSEG look-up and chain checks."""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, Field

# Strict on purpose: RICs end up inside LSEG search filters, so no quotes or spaces.
RIC_PATTERN = r"^[A-Za-z0-9.^=_\-]{1,32}$"
CHAIN_PATTERN = r"^[A-Za-z0-9.^=_\-#*+:]{1,64}$"

Ric = Field(pattern=RIC_PATTERN)
ExpiryFilter = Literal["all", "monthly"]


@lru_cache(maxsize=1)
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def _check_zone(v: str | None) -> str | None:
    if v is not None and v not in _zones():
        raise ValueError(f"unknown time zone '{v}' (use an IANA name such as America/New_York)")
    return v


TimeZone = Annotated[str | None, AfterValidator(_check_zone)]


class NameOut(BaseModel):
    name_id: int
    name: str
    chain_ric: str | None
    display_name: str | None
    active: bool
    group_name: str | None = None
    expiry_filter: ExpiryFilter = "all"
    timezone: str | None = None
    last_snapshot_ts: datetime | None = None


class NameIn(BaseModel):
    name: str = Field(pattern=RIC_PATTERN)
    chain_ric: str = Field(pattern=CHAIN_PATTERN)
    display_name: str | None = Field(default=None, max_length=128)
    group_name: str | None = Field(default=None, max_length=32)
    expiry_filter: ExpiryFilter = "all"
    active: bool = True
    timezone: TimeZone = None


class NamePatch(BaseModel):
    chain_ric: str | None = Field(default=None, pattern=CHAIN_PATTERN)
    display_name: str | None = Field(default=None, max_length=128)
    group_name: str | None = Field(default=None, max_length=32)
    expiry_filter: ExpiryFilter | None = None
    active: bool | None = None
    timezone: TimeZone = None


class LookupRequest(BaseModel):
    rics: list[str] = Field(min_length=1, max_length=60)


class ChainCheckRequest(BaseModel):
    name: str = Field(pattern=RIC_PATTERN)
    chain_ric: str = Field(pattern=CHAIN_PATTERN)


class ChainCandidateOut(BaseModel):
    chain_ric: str
    title: str
    preferred: bool


class NameLookupOut(BaseModel):
    ric: str
    found: bool
    display_name: str | None
    spot: float | None
    currency: str | None
    vol: float | None
    candidates: list[ChainCandidateOut]
    error: str | None
    timezone_guess: str | None = None  # from the RIC; pre-fills the name's time zone
    registered: bool = False          # already in the names table


class ChainCheckOut(BaseModel):
    name: str
    chain_ric: str
    n_options: int
    n_expiries: int
    first_expiry: date | None
    last_expiry: date | None
    strike_min: float | None
    strike_max: float | None
    underlying_match: float | None
    duration_sec: float
