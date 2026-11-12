"""Local snap times -> UTC firings, including both daylight-saving changes in the US and EU."""
from __future__ import annotations

from datetime import date, datetime, time

from vol_fitter.scheduling.clock import (
    days_to_mask, firings_between, local_to_utc, mask_to_days, next_firing,
)
from vol_fitter.scheduling.models import WEEKDAYS_MASK, ScheduleEntry

NY, BERLIN = "America/New_York", "Europe/Berlin"


def _entry(tz=NY, times=(time(15, 45),), days=WEEKDAYS_MASK):
    return ScheduleEntry(name_id=1, name="X", timezone=tz, days=days, times=tuple(times))


def test_winter_and_summer_offsets():
    assert local_to_utc(date(2026, 11, 12), time(15, 45), NY) == datetime(2026, 11, 12, 20, 45)   # EST, UTC-5
    assert local_to_utc(date(2026, 7, 15), time(15, 45), NY) == datetime(2026, 7, 15, 19, 45)     # EDT, UTC-4
    assert local_to_utc(date(2026, 11, 12), time(17, 15), BERLIN) == datetime(2026, 11, 12, 16, 15)


def test_us_spring_forward_gap_fires_an_hour_later():
    # 2026-03-08 02:30 doesn't exist in New York; it fires at 03:30 EDT = 07:30 UTC.
    assert local_to_utc(date(2026, 3, 8), time(2, 30), NY) == datetime(2026, 3, 8, 7, 30)


def test_us_fall_back_ambiguous_time_fires_once_at_first_occurrence():
    e = _entry(times=(time(1, 30),), days=127)
    fires = firings_between(e, datetime(2026, 11, 1, 0, 0), datetime(2026, 11, 2, 0, 0))
    assert [f.fire_utc for f in fires] == [datetime(2026, 11, 1, 5, 30)]      # 01:30 EDT, not also 01:30 EST


def test_eu_changes_follow_their_own_dates():
    assert local_to_utc(date(2026, 3, 27), time(9, 45), BERLIN) == datetime(2026, 3, 27, 8, 45)   # CET
    assert local_to_utc(date(2026, 3, 30), time(9, 45), BERLIN) == datetime(2026, 3, 30, 7, 45)   # CEST
    assert local_to_utc(date(2026, 10, 26), time(9, 45), BERLIN) == datetime(2026, 10, 26, 8, 45)  # CET again


def test_days_mask_skips_weekend():
    e = _entry(times=(time(9, 45),))
    fires = firings_between(e, datetime(2026, 11, 13, 0, 0), datetime(2026, 11, 17, 0, 0))   # Fri..Mon
    assert [f.fire_utc.date() for f in fires] == [date(2026, 11, 13), date(2026, 11, 16)]
    assert mask_to_days(days_to_mask(["Mon", "Wed", "Sun"])) == ["Mon", "Wed", "Sun"]


def test_window_is_open_closed_and_handles_midnight_wrap():
    e = _entry(tz="Asia/Tokyo", times=(time(8, 0),), days=127)      # 08:00 JST = 23:00 UTC the day before
    fires = firings_between(e, datetime(2026, 11, 12, 22, 0), datetime(2026, 11, 12, 23, 0))
    assert [f.fire_utc for f in fires] == [datetime(2026, 11, 12, 23, 0)]
    assert firings_between(e, datetime(2026, 11, 12, 23, 0), datetime(2026, 11, 12, 23, 30)) == []


def test_labels_and_next_firing():
    e = _entry(times=(time(9, 45), time(15, 45)))
    nxt = next_firing(e, datetime(2026, 11, 12, 15, 0))              # 10:00 EST Thursday
    assert nxt.fire_utc == datetime(2026, 11, 12, 20, 45) and nxt.local_label == "15:45 EST"
    assert next_firing(_entry(tz=None), datetime(2026, 11, 12)) is None
