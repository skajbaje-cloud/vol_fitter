"""Which listed expiries a name snaps: all of them, or only the standard monthlies."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

EXPIRY_FILTERS = ("all", "monthly")


def third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def monthly_expiries(expiries) -> set[date]:
    """Standard monthly expiries among `expiries`: the third Friday, or the Thursday
    before it when the Friday is an exchange holiday (and so isn't listed)."""
    listed = {pd.Timestamp(e).date() for e in expiries}
    keep = set()
    for d in listed:
        tf = third_friday(d.year, d.month)
        if d == tf or (d == tf - timedelta(days=1) and tf not in listed):
            keep.add(d)
    return keep


def filter_expiries(universe: pd.DataFrame, mode: str, col: str = "EXPIR_DATE") -> pd.DataFrame:
    if mode in (None, "", "all"):
        return universe
    if mode != "monthly":
        raise ValueError(f"unknown expiry filter '{mode}' (expected one of {EXPIRY_FILTERS})")
    keep = monthly_expiries(universe[col].unique())
    return universe[pd.to_datetime(universe[col]).dt.date.isin(keep)]
