"""Thin, generic read/write layer over the vol_fitter MySQL schema.

No pricing/snapshot-domain logic here on purpose — this class only knows
how to move rows (dataclasses for single-row tables, DataFrames for bulk
tables) in and out of the tables defined in schema.py. Smile-fit queries
live in fit_queries.py (mixed in).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy import Table, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import Engine

from vol_fitter.db import schema
from vol_fitter.db.fit_queries import FitQueriesMixin
from vol_fitter.db.models import NameRecord, SnapshotRecord
from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class VolFitterRepository(FitQueriesMixin):
    def __init__(self, engine: Engine):
        self.engine = engine

    # ---- names (control table) ----

    def get_or_create_name_id(self, record: NameRecord) -> int:
        """Insert the name if new, or refresh its chain_ric/display_name/active
        if it already exists; either way, returns its name_id."""
        stmt = mysql_insert(schema.names).values(
            name=record.name,
            chain_ric=record.chain_ric,
            display_name=record.display_name,
            active=record.active,
            created_ts=_utcnow(),
        )
        stmt = stmt.on_duplicate_key_update(
            chain_ric=stmt.inserted.chain_ric,
            display_name=stmt.inserted.display_name,
            active=stmt.inserted.active,
            # MySQL trick to get the existing row's PK back out of an
            # INSERT ... ON DUPLICATE KEY UPDATE via result.lastrowid.
            name_id=func.last_insert_id(schema.names.c.name_id),
        )
        with self.engine.begin() as conn:
            result = conn.execute(stmt)
            name_id = result.lastrowid
        logger.info("Registered/updated name '%s' -> name_id=%s", record.name, name_id)
        return name_id

    def get_name(self, name: str) -> NameRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(schema.names).where(schema.names.c.name == name)).first()
        if row is None:
            return None
        return NameRecord(
            name=row.name, chain_ric=row.chain_ric,
            display_name=row.display_name, active=row.active, name_id=row.name_id,
        )

    # ---- snapshots (one row per name per snapshot) ----

    def upsert_snapshot(self, record: SnapshotRecord) -> None:
        stmt = mysql_insert(schema.snapshots).values(
            name_id=record.name_id,
            snapshot_ts=record.snapshot_ts,
            spot=record.spot,
            universe_size=record.universe_size,
            window_size=record.window_size,
            snap_duration_sec=record.snap_duration_sec,
            status=record.status,
        )
        update_cols = {
            c.name: stmt.inserted[c.name]
            for c in schema.snapshots.columns
            if c.name not in ("name_id", "snapshot_ts")
        }
        with self.engine.begin() as conn:
            conn.execute(stmt.on_duplicate_key_update(**update_cols))

    # ---- bulk tables ----

    def insert_quotes(self, df: pd.DataFrame) -> int:
        return self._upsert_df(schema.raw_quotes, df, key_cols=("name_id", "snapshot_ts", "instrument"))

    def upsert_maturity_params(self, df: pd.DataFrame) -> int:
        return self._upsert_df(schema.maturity_params, df, key_cols=("name_id", "snapshot_ts", "expiry_date"))

    def upsert_master_params(self, df: pd.DataFrame) -> int:
        return self._upsert_df(schema.master_params, df, key_cols=("name_id", "snapshot_ts"))

    def _upsert_df(self, table: Table, df: pd.DataFrame, key_cols: tuple[str, ...]) -> int:
        if df.empty:
            return 0
        # pymysql has no wire representation for NaN -- it must be NULL.
        # astype(object) first so the None survives to_dict() instead of
        # pandas silently upcasting it back to NaN in a float column.
        records = df.astype(object).where(df.notna(), None).to_dict("records")
        stmt = mysql_insert(table)
        # Only reference columns actually present in the INSERT's column
        # list (i.e. present in df) -- referencing a table column that
        # wasn't part of this particular insert raises "Unknown column
        # 'new.<col>'" in MySQL's ON DUPLICATE KEY UPDATE.
        update_cols = {
            c.name: stmt.inserted[c.name]
            for c in table.columns
            if c.name in df.columns and c.name not in key_cols and not c.primary_key
        }
        with self.engine.begin() as conn:
            conn.execute(stmt.on_duplicate_key_update(**update_cols), records)
        logger.debug("Upserted %d rows into %s", len(records), table.name)
        return len(records)

    # ---- reads ----

    def list_names(self, active_only: bool = False) -> list[NameRecord]:
        query = select(schema.names).order_by(schema.names.c.name)
        if active_only:
            query = query.where(schema.names.c.active.is_(True))
        with self.engine.connect() as conn:
            rows = conn.execute(query).all()
        return [
            NameRecord(name=r.name, chain_ric=r.chain_ric, display_name=r.display_name,
                       active=bool(r.active), name_id=r.name_id)
            for r in rows
        ]

    def list_snapshot_timestamps(self, name_id: int) -> list[datetime]:
        """Snapshots that produced priced data (maturity_params rows), newest first."""
        mp = schema.maturity_params
        query = (
            select(mp.c.snapshot_ts).where(mp.c.name_id == name_id)
            .group_by(mp.c.snapshot_ts).order_by(mp.c.snapshot_ts.desc())
        )
        with self.engine.connect() as conn:
            return [r.snapshot_ts for r in conn.execute(query)]

    def list_maturities(self, name_id: int, snapshot_ts: datetime) -> list[date]:
        mp = schema.maturity_params
        query = (
            select(mp.c.expiry_date)
            .where(mp.c.name_id == name_id, mp.c.snapshot_ts == snapshot_ts)
            .order_by(mp.c.expiry_date)
        )
        with self.engine.connect() as conn:
            return [r.expiry_date for r in conn.execute(query)]

    def fetch_quotes(self, name_id: int, snapshot_ts: datetime, expiry_date: date | None = None) -> pd.DataFrame:
        rq = schema.raw_quotes
        query = select(rq).where(rq.c.name_id == name_id, rq.c.snapshot_ts == snapshot_ts)
        if expiry_date is not None:
            query = query.where(rq.c.expiry_date == expiry_date)
        return pd.read_sql(query, self.engine)

    def fetch_maturity_params(
        self, name_id: int, snapshot_ts: datetime | None = None, expiry_date: date | None = None,
    ) -> pd.DataFrame:
        mp = schema.maturity_params
        query = select(mp).where(mp.c.name_id == name_id)
        if snapshot_ts is not None:
            query = query.where(mp.c.snapshot_ts == snapshot_ts)
        if expiry_date is not None:
            query = query.where(mp.c.expiry_date == expiry_date)
        return pd.read_sql(query, self.engine)

    def fetch_snapshot(self, name_id: int, snapshot_ts: datetime) -> dict | None:
        s = schema.snapshots
        with self.engine.connect() as conn:
            row = conn.execute(select(s).where(s.c.name_id == name_id, s.c.snapshot_ts == snapshot_ts)).first()
        return dict(row._mapping) if row else None
