"""The `names` control table, mixed into VolFitterRepository (kept apart to keep files small)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from vol_fitter.db import schema
from vol_fitter.db.models import NameRecord
from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)

# Columns a caller may change on an existing name (name and name_id are identity).
EDITABLE_NAME_FIELDS = ("chain_ric", "display_name", "active", "group_name", "expiry_filter", "timezone")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_record(row) -> NameRecord:
    return NameRecord(
        name=row.name, chain_ric=row.chain_ric, display_name=row.display_name, active=bool(row.active),
        group_name=row.group_name, expiry_filter=row.expiry_filter or "all", timezone=row.timezone,
        name_id=row.name_id,
    )


class NameQueriesMixin:
    """Needs self.engine from VolFitterRepository."""

    def get_or_create_name_id(self, record: NameRecord) -> int:
        """Insert the name if new, or overwrite every editable field if it exists; returns its name_id."""
        values = {f: getattr(record, f) for f in EDITABLE_NAME_FIELDS}
        stmt = mysql_insert(schema.names).values(name=record.name, created_ts=_utcnow(), **values)
        stmt = stmt.on_duplicate_key_update(
            **{f: stmt.inserted[f] for f in EDITABLE_NAME_FIELDS},
            # MySQL trick to get the existing row's PK back out of an
            # INSERT ... ON DUPLICATE KEY UPDATE via result.lastrowid.
            name_id=func.last_insert_id(schema.names.c.name_id),
        )
        with self.engine.begin() as conn:
            name_id = conn.execute(stmt).lastrowid
        logger.info("Registered/updated name '%s' -> name_id=%s", record.name, name_id)
        return name_id

    def ensure_name_id(self, name: str, chain_ric: str | None = None) -> int:
        """name_id of an existing name, untouched; registers it (needs chain_ric) only if missing."""
        existing = self.get_name(name)
        if existing is not None:
            return existing.name_id
        return self.get_or_create_name_id(NameRecord(name=name, chain_ric=chain_ric))

    def update_name(self, name: str, **fields) -> NameRecord | None:
        unknown = set(fields) - set(EDITABLE_NAME_FIELDS)
        if unknown:
            raise ValueError(f"not editable: {sorted(unknown)}")
        if fields:
            with self.engine.begin() as conn:
                conn.execute(update(schema.names).where(schema.names.c.name == name).values(**fields))
            logger.info("updated name '%s': %s", name, fields)
        return self.get_name(name)

    def get_name(self, name: str) -> NameRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(schema.names).where(schema.names.c.name == name)).first()
        return _to_record(row) if row else None

    def list_names(self, active_only: bool = False) -> list[NameRecord]:
        query = select(schema.names).order_by(schema.names.c.name)
        if active_only:
            query = query.where(schema.names.c.active.is_(True))
        with self.engine.connect() as conn:
            return [_to_record(r) for r in conn.execute(query).all()]

    def last_snapshot_times(self) -> dict[int, datetime]:
        """name_id -> timestamp of its latest priced snapshot (names never snapped are absent)."""
        mp = schema.maturity_params
        query = select(mp.c.name_id, func.max(mp.c.snapshot_ts).label("ts")).group_by(mp.c.name_id)
        with self.engine.connect() as conn:
            return {r.name_id: r.ts for r in conn.execute(query)}

