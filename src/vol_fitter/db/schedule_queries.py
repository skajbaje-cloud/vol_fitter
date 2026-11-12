"""Snapshot-schedule tables (snap_schedules, snap_slots, schedule_runs, app_settings), mixed into VolFitterRepository."""
from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError

from vol_fitter.db import schema
from vol_fitter.logging_setup import get_logger
from vol_fitter.scheduling.models import WEEKDAYS_MASK, ScheduleEntry, ScheduleRun

logger = get_logger(__name__)

OPEN_STATUS = "queued"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ScheduleQueriesMixin:
    """Needs self.engine from VolFitterRepository."""

    def list_schedules(self) -> list[ScheduleEntry]:
        """One entry per registered name; names never scheduled get the defaults and no times."""
        n, s, sl = schema.names, schema.snap_schedules, schema.snap_slots
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(n.c.name_id, n.c.name, n.c.timezone, n.c.active, s.c.days, s.c.enabled)
                .select_from(n.outerjoin(s, s.c.name_id == n.c.name_id)).order_by(n.c.name)
            ).all()
            slots = conn.execute(select(sl.c.name_id, sl.c.local_time).order_by(sl.c.local_time)).all()
        times: dict[int, list[time]] = {}
        for r in slots:
            times.setdefault(r.name_id, []).append(r.local_time)
        return [
            ScheduleEntry(
                name_id=r.name_id, name=r.name, timezone=r.timezone,
                days=WEEKDAYS_MASK if r.days is None else int(r.days),
                enabled=True if r.enabled is None else bool(r.enabled),
                active=bool(r.active), times=tuple(times.get(r.name_id, ())),
            )
            for r in rows
        ]

    def replace_schedules(self, items: list[tuple[int, list[time], int, bool]]) -> None:
        """Overwrite (name_id, times, days, enabled) for each item, all in one transaction."""
        s, sl = schema.snap_schedules, schema.snap_slots
        now = _utcnow()
        with self.engine.begin() as conn:
            for name_id, times, days, enabled in items:
                stmt = mysql_insert(s).values(name_id=name_id, days=days, enabled=enabled, updated_ts=now)
                conn.execute(stmt.on_duplicate_key_update(days=days, enabled=enabled, updated_ts=now))
                conn.execute(delete(sl).where(sl.c.name_id == name_id))
                if times:
                    conn.execute(sl.insert(), [{"name_id": name_id, "local_time": t} for t in times])
        logger.info("saved schedules for %d names", len(items))

    def insert_run(self, name_id: int, scheduled_for_utc: datetime, local_label: str, status: str,
                   job_id: int | None = None, reason: str | None = None) -> int | None:
        """Claim a firing: the new run's id, or None if that (name, instant) was already recorded."""
        row = dict(name_id=name_id, scheduled_for_utc=scheduled_for_utc, local_label=local_label,
                   status=status, job_id=job_id, reason=reason, created_ts=_utcnow())
        try:
            with self.engine.begin() as conn:
                return conn.execute(schema.schedule_runs.insert().values(**row)).inserted_primary_key[0]
        except IntegrityError:
            return None

    def update_run(self, run_id: int, **fields) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(schema.schedule_runs).where(schema.schedule_runs.c.id == run_id).values(**fields))

    def open_runs(self) -> list[ScheduleRun]:
        return self._runs(schema.schedule_runs.c.status == OPEN_STATUS, limit=None)

    def recent_runs(self, limit: int = 20) -> list[ScheduleRun]:
        return self._runs(None, limit=limit)

    def last_runs(self) -> dict[int, ScheduleRun]:
        """name_id -> its most recent run."""
        r = schema.schedule_runs
        latest = select(r.c.name_id, func.max(r.c.scheduled_for_utc).label("ts")).group_by(r.c.name_id).subquery()
        cond = (r.c.name_id == latest.c.name_id) & (r.c.scheduled_for_utc == latest.c.ts)
        return {x.name_id: x for x in self._runs(None, limit=None, join=(latest, cond))}

    def _runs(self, where, limit: int | None, join=None) -> list[ScheduleRun]:
        r, n = schema.schedule_runs, schema.names
        src = r.join(n, n.c.name_id == r.c.name_id)
        if join is not None:
            src = src.join(join[0], join[1])
        query = select(r, n.c.name).select_from(src).order_by(r.c.scheduled_for_utc.desc(), r.c.id.desc())
        if where is not None:
            query = query.where(where)
        if limit:
            query = query.limit(limit)
        with self.engine.connect() as conn:
            rows = conn.execute(query).all()
        return [ScheduleRun(id=x.id, name_id=x.name_id, name=x.name, scheduled_for_utc=x.scheduled_for_utc,
                            local_label=x.local_label, status=x.status, job_id=x.job_id, reason=x.reason)
                for x in rows]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.engine.connect() as conn:
            value = conn.execute(select(schema.app_settings.c.value).where(schema.app_settings.c.key == key)).scalar()
        return default if value is None else value

    def set_setting(self, key: str, value: str) -> None:
        stmt = mysql_insert(schema.app_settings).values(key=key, value=value)
        with self.engine.begin() as conn:
            conn.execute(stmt.on_duplicate_key_update(value=value))

    def last_snap_durations(self) -> dict[int, float]:
        """name_id -> snap_duration_sec of its latest snapshot (for the schedule's load estimate)."""
        s = schema.snapshots
        latest = select(s.c.name_id, func.max(s.c.snapshot_ts).label("ts")).group_by(s.c.name_id).subquery()
        query = select(s.c.name_id, s.c.snap_duration_sec).join(
            latest, (s.c.name_id == latest.c.name_id) & (s.c.snapshot_ts == latest.c.ts))
        with self.engine.connect() as conn:
            return {r.name_id: float(r.snap_duration_sec) for r in conn.execute(query) if r.snap_duration_sec is not None}
