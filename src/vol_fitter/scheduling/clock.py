"""Pure time arithmetic for the scheduler: local wall-clock slots -> UTC firing instants.

All datetimes going in and out are naive UTC (as stored in MySQL). Local times
follow the name's IANA zone through daylight-saving changes:
  * a slot that doesn't exist on the spring-forward day (02:30 in New York)
    fires an hour later in wall-clock terms (zoneinfo's fold=0 behaviour);
  * a slot that occurs twice on the fall-back day fires once, at the first one.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from vol_fitter.logging_setup import get_logger
from vol_fitter.scheduling.models import DAY_NAMES, Firing, ScheduleEntry

logger = get_logger(__name__)

UTC = timezone.utc


def local_to_utc(d: date, t: time, tz: str) -> datetime:
    """Naive UTC instant of wall-clock time t on local date d in zone tz."""
    local = datetime.combine(d, t).replace(tzinfo=ZoneInfo(tz), fold=0)
    return local.astimezone(UTC).replace(tzinfo=None)


def local_label(fire_utc: datetime, tz: str) -> str:
    local = fire_utc.replace(tzinfo=UTC).astimezone(ZoneInfo(tz))
    return f"{local:%H:%M} {local.tzname()}"


def runs_on(entry: ScheduleEntry, d: date) -> bool:
    return bool(entry.days & (1 << d.weekday()))


def days_to_mask(days: list[str]) -> int:
    return sum(1 << DAY_NAMES.index(d) for d in set(days))


def mask_to_days(mask: int) -> list[str]:
    return [d for i, d in enumerate(DAY_NAMES) if mask & (1 << i)]


def firings_between(entry: ScheduleEntry, start_utc: datetime, end_utc: datetime) -> list[Firing]:
    """Every firing of entry with start_utc < fire <= end_utc, oldest first (ignores enabled/active)."""
    if not entry.timezone or not entry.times or end_utc <= start_utc:
        return []
    zone = ZoneInfo(entry.timezone)
    first = start_utc.replace(tzinfo=UTC).astimezone(zone).date() - timedelta(days=1)
    last = end_utc.replace(tzinfo=UTC).astimezone(zone).date() + timedelta(days=1)
    seen: set[datetime] = set()
    out: list[Firing] = []
    d = first
    while d <= last:
        if runs_on(entry, d):
            for t in entry.times:
                fire = local_to_utc(d, t, entry.timezone)
                if start_utc < fire <= end_utc and fire not in seen:
                    seen.add(fire)
                    out.append(Firing(entry.name_id, entry.name, fire, local_label(fire, entry.timezone)))
        d += timedelta(days=1)
    return sorted(out, key=lambda f: f.fire_utc)


def next_firing(entry: ScheduleEntry, now_utc: datetime, horizon_days: int = 8) -> Firing | None:
    """The first firing after now_utc within horizon_days, or None."""
    found = firings_between(entry, now_utc, now_utc + timedelta(days=horizon_days))
    return found[0] if found else None
