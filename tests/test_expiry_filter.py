"""Market-specific monthly expiries, and the empty-snapshot guard (pure logic, no LSEG)."""
from datetime import date

import pandas as pd
import pytest

from vol_fitter.snapshot.expiry_filter import filter_expiries, monthly_expiries, nth_last_business_day
from vol_fitter.snapshot.snapshot_service import EmptySnapshotError, SnapshotService

# Nikkei chain as listed by LSEG on 2026-11-12: all second Fridays.
N225 = [date(2026, 11, 13), date(2026, 12, 11), date(2027, 1, 8), date(2027, 3, 12)]


def test_japan_monthlies_are_second_fridays():
    assert monthly_expiries(N225, "Asia/Tokyo") == set(N225)
    assert monthly_expiries(N225, "America/New_York") == set()      # the old 3rd-Friday rule kept none


def test_japan_drops_weeklies():
    weeklies = [date(2026, 11, 6), date(2026, 11, 20), date(2026, 11, 27)]
    assert monthly_expiries(N225 + weeklies, "Asia/Tokyo") == set(N225)


def test_korea_second_thursday():
    listed = [date(2026, 11, 5), date(2026, 11, 12), date(2026, 11, 19), date(2025, 8, 7), date(2025, 8, 14)]
    # Aug 2025 starts on a Friday: the 2nd Thursday is the 14th, not the 7th (the Thursday before the 2nd Friday).
    assert monthly_expiries(listed, "Asia/Seoul") == {date(2026, 11, 12), date(2025, 8, 14)}


def test_hong_kong_second_last_business_day():
    assert nth_last_business_day(2026, 11, 2) == date(2026, 11, 27)   # Nov 30 is a Monday
    assert nth_last_business_day(2026, 12, 2) == date(2026, 12, 30)
    listed = [date(2026, 11, 26), date(2026, 11, 27), date(2026, 12, 30)]
    assert monthly_expiries(listed, "Asia/Hong_Kong") == {date(2026, 11, 27), date(2026, 12, 30)}


def test_holiday_rolls_back_to_the_previous_listed_day():
    listed = [date(2027, 2, 10), date(2027, 2, 24)]           # 2027-02-12 (2nd Fri) not listed; Wed 10th is
    assert monthly_expiries(listed, "Asia/Tokyo") == {date(2027, 2, 10)}
    assert monthly_expiries([date(2027, 2, 5)], "Asia/Tokyo") == set()   # a week early is not a roll-back


def test_unknown_zone_uses_third_friday():
    listed = [date(2026, 11, 13), date(2026, 11, 20)]
    assert monthly_expiries(listed, None) == {date(2026, 11, 20)}
    assert monthly_expiries(listed, "Europe/Berlin") == {date(2026, 11, 20)}


class _Cache:
    def __init__(self, frame):
        self.frame = frame

    def load(self):
        return self.frame


def _universe(expiries):
    return pd.DataFrame({"Instrument": [f"X{i}" for i in range(len(expiries))], "STRIKE_PRC": 100.0,
                         "EXPIR_DATE": [str(e) for e in expiries], "T": 0.1, "is_call": True})


def test_filter_frame_uses_market():
    assert len(filter_expiries(_universe(N225), "monthly", "Asia/Tokyo")) == 4
    assert len(filter_expiries(_universe(N225), "monthly")) == 0


def test_empty_filter_fails_before_touching_lseg():
    svc = SnapshotService(client=None, universe_cache=_Cache(_universe(N225)), underlying=".N225", expiry_filter="monthly")
    with pytest.raises(EmptySnapshotError, match="kept 0 of 4 listed expiries"):
        svc.snap()
