"""Which listed expiries a name snaps: all of them, or only the standard monthlies.

What counts as "the monthly" depends on the market, which we read off the name's
exchange time zone. Each rule gives the nominal date for a month; when that date
isn't listed (an exchange holiday), the nearest listed expiry up to 3 days earlier
is taken instead, which is how exchanges roll a holiday expiry.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Callable

import pandas as pd

from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)

EXPIRY_FILTERS = ("all", "monthly")
MON, TUE, WED, THU, FRI = range(5)
HOLIDAY_ROLLBACK_DAYS = 3


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th `weekday` (Mon=0) of the month, n counted from 1."""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def nth_last_business_day(year: int, month: int, n: int) -> date:
    """The n-th last Mon-Fri of the month (n=1 is the last); holidays are left to the roll-back."""
    d = date(year, month, calendar.monthrange(year, month)[1])
    while True:
        if d.weekday() < 5:
            n -= 1
            if n == 0:
                return d
        d -= timedelta(days=1)


def third_friday(year: int, month: int) -> date:
    return nth_weekday(year, month, FRI, 3)


MonthlyRule = Callable[[int, int], date]
DEFAULT_RULE: tuple[str, MonthlyRule] = ("3rd Friday", third_friday)
# Exchange time zone -> (description, nominal monthly expiry). Anything else uses DEFAULT_RULE (US, Europe).
MARKET_RULES: dict[str, tuple[str, MonthlyRule]] = {
    "Asia/Tokyo": ("2nd Friday (SQ)", lambda y, m: nth_weekday(y, m, FRI, 2)),
    "Asia/Seoul": ("2nd Thursday", lambda y, m: nth_weekday(y, m, THU, 2)),
    "Asia/Hong_Kong": ("2nd-last business day", lambda y, m: nth_last_business_day(y, m, 2)),
    "Asia/Taipei": ("3rd Wednesday", lambda y, m: nth_weekday(y, m, WED, 3)),
    "Australia/Sydney": ("3rd Thursday", lambda y, m: nth_weekday(y, m, THU, 3)),
    "Asia/Kolkata": ("last Tuesday", lambda y, m: last_weekday(y, m, TUE)),
}


def monthly_rule(timezone: str | None) -> tuple[str, MonthlyRule]:
    return MARKET_RULES.get(timezone or "", DEFAULT_RULE)


def monthly_expiries(expiries, timezone: str | None = None) -> set[date]:
    """Standard monthly expiries among `expiries` for the market of `timezone`."""
    listed = {pd.Timestamp(e).date() for e in expiries}
    _, rule = monthly_rule(timezone)
    keep = set()
    for y, m in {(d.year, d.month) for d in listed}:
        nominal = rule(y, m)
        if nominal in listed:
            keep.add(nominal)
            continue
        earlier = [d for d in listed if nominal - timedelta(days=HOLIDAY_ROLLBACK_DAYS) <= d < nominal]
        if earlier:
            keep.add(max(earlier))
    return keep


def filter_expiries(universe: pd.DataFrame, mode: str, timezone: str | None = None, col: str = "EXPIR_DATE") -> pd.DataFrame:
    if mode in (None, "", "all"):
        return universe
    if mode != "monthly":
        raise ValueError(f"unknown expiry filter '{mode}' (expected one of {EXPIRY_FILTERS})")
    keep = monthly_expiries(universe[col].unique(), timezone)
    logger.debug("monthly filter (%s, %s): kept %d expiries", timezone, monthly_rule(timezone)[0], len(keep))
    return universe[pd.to_datetime(universe[col]).dt.date.isin(keep)]
