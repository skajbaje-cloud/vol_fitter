"""Thin, generic read/write layer over the vol_fitter MySQL schema.

No pricing/snapshot-domain logic here on purpose — this class only knows
how to move rows (dataclasses for single-row tables, DataFrames for bulk
tables) in and out of the five tables defined in schema.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import Table, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import Engine

from vol_fitter.db import schema
from vol_fitter.db.models import NameRecord, SnapshotRecord
from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class VolFitterRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    # ---- names (control table) ----

    def get_or_create_name_id(self, record: NameRecord) -> int:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(schema.names.c.name_id).where(schema.names.c.name == record.name)
            ).first()
            if row is not None:
                return row.name_id
            result = conn.execute(
                schema.names.insert().values(
                    name=record.name,
                    chain_ric=record.chain_ric,
                    display_name=record.display_name,
                    active=record.active,
                    created_ts=_utcnow(),
                )
            )
            name_id = result.inserted_primary_key[0]
        logger.info("Registered new name '%s' -> name_id=%s", record.name, name_id)
        return name_id

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
        records = df.to_dict("records")
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

    def fetch_quotes(self, name_id: int, snapshot_ts: datetime) -> pd.DataFrame:
        query = select(schema.raw_quotes).where(
            schema.raw_quotes.c.name_id == name_id,
            schema.raw_quotes.c.snapshot_ts == snapshot_ts,
        )
        return pd.read_sql(query, self.engine)

    def fetch_maturity_params(self, name_id: int, snapshot_ts: datetime | None = None) -> pd.DataFrame:
        query = select(schema.maturity_params).where(schema.maturity_params.c.name_id == name_id)
        if snapshot_ts is not None:
            query = query.where(schema.maturity_params.c.snapshot_ts == snapshot_ts)
        return pd.read_sql(query, self.engine)
