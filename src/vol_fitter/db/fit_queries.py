"""Smile-fit reads/writes, mixed into VolFitterRepository (kept apart to keep files small)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import case, func, select

from vol_fitter.db import schema


class FitQueriesMixin:
    """Needs self.engine and self._upsert_df from VolFitterRepository."""

    def upsert_fit_quotes(self, df: pd.DataFrame) -> int:
        return self._upsert_df(schema.fit_quotes, df, key_cols=("name_id", "snapshot_ts", "instrument"))

    def fetch_fit_quotes(self, name_id: int, snapshot_ts: datetime, expiry_date: date | None = None) -> pd.DataFrame:
        fq = schema.fit_quotes
        query = select(fq).where(fq.c.name_id == name_id, fq.c.snapshot_ts == snapshot_ts)
        if expiry_date is not None:
            query = query.where(fq.c.expiry_date == expiry_date)
        return pd.read_sql(query, self.engine)

    def fetch_previous_fits(self, name_id: int, before_ts: datetime, max_age_days: float) -> pd.DataFrame:
        """Latest successful fit per expiry strictly before before_ts, no older than max_age_days.

        One row per expiry_date with snapshot_ts and the four smile params.
        """
        mp = schema.maturity_params
        query = (
            select(mp.c.expiry_date, mp.c.snapshot_ts, mp.c.sigma_atm, mp.c.skew, mp.c.kappa_put, mp.c.kappa_call)
            .where(
                mp.c.name_id == name_id,
                mp.c.snapshot_ts < before_ts,
                mp.c.snapshot_ts >= before_ts - timedelta(days=max_age_days),
                mp.c.fit_status == "ok",
            )
            .order_by(mp.c.snapshot_ts.desc())
        )
        df = pd.read_sql(query, self.engine)
        return df.drop_duplicates("expiry_date", keep="first").reset_index(drop=True)

    def list_unfitted_snapshots(self, name_id: int) -> list[datetime]:
        """Snapshots with forwards but no smile fit on any expiry yet, oldest first."""
        mp = schema.maturity_params
        query = (
            select(mp.c.snapshot_ts).where(mp.c.name_id == name_id)
            .group_by(mp.c.snapshot_ts)
            .having(func.count(mp.c.fit_status) == 0)   # COUNT(col) skips NULLs
            .order_by(mp.c.snapshot_ts)
        )
        with self.engine.connect() as conn:
            return [r.snapshot_ts for r in conn.execute(query)]

    def fit_coverage(self) -> pd.DataFrame:
        """One row per (name, snapshot): how many expiries are fitted, how well, and when."""
        mp, n = schema.maturity_params, schema.names
        query = (
            select(
                n.c.name, mp.c.snapshot_ts,
                func.count().label("n_expiries"),
                func.count(mp.c.fit_status).label("n_fitted"),
                func.sum(case((mp.c.fit_status == "ok", 1), else_=0)).label("n_ok"),
                func.avg(mp.c.pct_inside).label("mean_pct_inside"),
                func.min(mp.c.pct_inside).label("min_pct_inside"),
                func.sum(mp.c.n_outliers).label("n_outliers"),
                func.max(mp.c.fit_ts).label("last_fit_ts"),
            )
            .select_from(mp.join(n, n.c.name_id == mp.c.name_id))
            .group_by(n.c.name, mp.c.snapshot_ts)
            .order_by(n.c.name, mp.c.snapshot_ts.desc())
        )
        return pd.read_sql(query, self.engine)
