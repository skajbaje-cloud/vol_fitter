"""Snap one underlying, price it, persist it -- shared by the CLI and the web job queue."""
from __future__ import annotations

import time

import pandas as pd

from vol_fitter.db import schema
from vol_fitter.db.models import NameRecord, SnapshotRecord
from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.logging_setup import get_logger
from vol_fitter.orchestration.models import SnapshotRunResult
from vol_fitter.pricing.black76_pricer import Black76Pricer
from vol_fitter.pricing.forward_fitter import ForwardFitter
from vol_fitter.snapshot.lseg_client import LsegClient
from vol_fitter.snapshot.snapshot_service import SnapshotService
from vol_fitter.snapshot.universe_cache import UniverseCache

logger = get_logger(__name__)

_RAW_QUOTE_COLS = [c.name for c in schema.raw_quotes.columns if c.name != "id"]
_MATURITY_COLS = [
    "name_id", "snapshot_ts", "expiry_date", "T", "forward", "discount_factor",
    "n_strikes_forward", "n_strikes_df", "forward_fit_resid", "df_fit_resid",
]


class UnregisteredNameError(ValueError):
    pass


def run_snapshot(repo: VolFitterRepository, underlying: str, chain_ric: str | None = None) -> SnapshotRunResult:
    """Snap `underlying`, fit forwards/DF, price every quote, persist all of it.

    chain_ric is only needed the first time a name is used; afterwards it's
    looked up from the `names` table.
    """
    t0 = time.time()
    existing = repo.get_name(underlying)
    chain_ric = chain_ric or (existing.chain_ric if existing else None)
    if not chain_ric:
        raise UnregisteredNameError(f"'{underlying}' isn't registered yet -- supply a chain_ric once to register it.")

    # An existing name's settings are left alone; a run only registers a name that's missing.
    name_id = existing.name_id if existing else repo.get_or_create_name_id(NameRecord(name=underlying, chain_ric=chain_ric))
    expiry_filter = existing.expiry_filter if existing else "all"

    with LsegClient() as client:
        universe_cache = UniverseCache(client, chain_ric, name=underlying)
        quotes, meta = SnapshotService(client, universe_cache, underlying, expiry_filter=expiry_filter,
                                       timezone=existing.timezone if existing else None).snap()

    forwards = ForwardFitter().fit_all(quotes)
    priced = Black76Pricer().price_quotes(quotes, forwards)
    priced["name_id"] = name_id
    priced["snapshot_ts"] = meta.snapshot_ts

    forwards_df = pd.DataFrame([f.__dict__ for f in forwards])
    forwards_df["name_id"] = name_id
    forwards_df["snapshot_ts"] = meta.snapshot_ts

    repo.upsert_snapshot(SnapshotRecord(
        name_id=name_id, snapshot_ts=meta.snapshot_ts, spot=meta.spot,
        universe_size=meta.universe_size, window_size=meta.window_size,
        snap_duration_sec=meta.snap_duration_sec, status=meta.status,
    ))
    n_quotes = repo.insert_quotes(priced.reindex(columns=_RAW_QUOTE_COLS))
    n_maturities = repo.upsert_maturity_params(forwards_df.reindex(columns=_MATURITY_COLS))
    logger.info("persisted %d quotes and %d maturity rows for %s @ %s",
                n_quotes, n_maturities, underlying, meta.snapshot_ts)

    return SnapshotRunResult(
        name=underlying, snapshot_ts=meta.snapshot_ts, spot=meta.spot, window_vol=meta.window_vol,
        universe_size=meta.universe_size, window_size=meta.window_size,
        n_quotes=n_quotes, n_maturities=n_maturities, duration_sec=time.time() - t0,
    )
