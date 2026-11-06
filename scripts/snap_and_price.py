"""Snap a live option chain, price it (forwards/IV/Greeks), persist to MySQL.

Usage:
    python scripts/snap_and_price.py --underlying .STOXX50E
    python scripts/snap_and_price.py --underlying .STOXX50E --chain-ric "0#STXE*.EX" --vol-ric .V6I3

chain-ric/vol-ric only need to be passed the first time a name is used (or
to change them); they're then stored in the `names` table and looked up by
--underlying automatically on later runs.

Requires a running, signed-in LSEG Workspace session and a .env with real
MySQL credentials (see .env.example); run `python -m vol_fitter.db.init_db`
once first to create the database and tables.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vol_fitter.db import schema
from vol_fitter.db.engine import build_engine
from vol_fitter.db.models import NameRecord, SnapshotRecord
from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.logging_setup import get_logger
from vol_fitter.pricing.black76_pricer import Black76Pricer
from vol_fitter.pricing.forward_fitter import ForwardFitter
from vol_fitter.snapshot.lseg_client import LsegClient
from vol_fitter.snapshot.snapshot_service import SnapshotService
from vol_fitter.snapshot.universe_cache import UniverseCache

logger = get_logger(__name__)

DEFAULT_UNDERLYING = ".STOXX50E"

_RAW_QUOTE_COLS = [c.name for c in schema.raw_quotes.columns if c.name != "id"]
_MATURITY_COLS = [
    "name_id", "snapshot_ts", "expiry_date", "T", "forward", "discount_factor",
    "n_strikes_forward", "n_strikes_df", "forward_fit_resid", "df_fit_resid",
]


def run(underlying: str, chain_ric: str | None = None, vol_ric: str | None = None) -> None:
    repo = VolFitterRepository(build_engine())
    existing = repo.get_name(underlying)
    chain_ric = chain_ric or (existing.chain_ric if existing else None)
    vol_ric = vol_ric or (existing.vol_ric if existing else None)
    if not chain_ric or not vol_ric:
        raise SystemExit(
            f"'{underlying}' isn't registered yet (or is missing chain_ric/vol_ric) -- "
            "pass --chain-ric and --vol-ric once to register it."
        )

    name_id = repo.get_or_create_name_id(
        NameRecord(name=underlying, chain_ric=chain_ric, vol_ric=vol_ric)
    )

    with LsegClient() as client:
        universe_cache = UniverseCache(client, chain_ric, name=underlying)
        service = SnapshotService(client, universe_cache, underlying, vol_ric)
        quotes, meta = service.snap()

    forwards = ForwardFitter().fit_all(quotes)
    priced = Black76Pricer().price_quotes(quotes, forwards)

    priced["name_id"] = name_id
    priced["snapshot_ts"] = meta.snapshot_ts

    forwards_df = pd.DataFrame([f.__dict__ for f in forwards])
    forwards_df["name_id"] = name_id
    forwards_df["snapshot_ts"] = meta.snapshot_ts

    repo.upsert_snapshot(
        SnapshotRecord(
            name_id=name_id,
            snapshot_ts=meta.snapshot_ts,
            spot=meta.spot,
            universe_size=meta.universe_size,
            window_size=meta.window_size,
            snap_duration_sec=meta.snap_duration_sec,
            status=meta.status,
        )
    )
    n_quotes = repo.insert_quotes(priced.reindex(columns=_RAW_QUOTE_COLS))
    n_maturities = repo.upsert_maturity_params(forwards_df.reindex(columns=_MATURITY_COLS))
    logger.info(
        "persisted %d quotes and %d maturity rows for %s @ %s",
        n_quotes, n_maturities, underlying, meta.snapshot_ts,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--underlying", default=DEFAULT_UNDERLYING)
    parser.add_argument("--chain-ric", default=None, help="only needed the first time this name is used")
    parser.add_argument("--vol-ric", default=None, help="only needed the first time this name is used")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.underlying, args.chain_ric, args.vol_ric)
