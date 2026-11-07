"""Snap a live option chain, price it (forwards/IV/Greeks), persist to MySQL.

Usage:
    python scripts/snap_and_price.py --underlying .STOXX50E
    python scripts/snap_and_price.py --underlying .STOXX50E --chain-ric "0#STXE*.EX"

chain-ric only needs to be passed the first time a name is used (or to
change it); it's then stored in the `names` table and looked up by
--underlying automatically on later runs. The window-sizing vol comes from
config.VOL_FIELD (TR.Volatility40D), requested directly on the underlying's
own RIC.

Requires a running, signed-in LSEG Workspace session and a .env with real
MySQL credentials (see .env.example); run `python -m vol_fitter.db.init_db`
once first to create the database and tables.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vol_fitter.db.engine import build_engine
from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.orchestration.snapshot_run import UnregisteredNameError, run_snapshot

DEFAULT_UNDERLYING = ".STOXX50E"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--underlying", default=DEFAULT_UNDERLYING)
    parser.add_argument("--chain-ric", default=None, help="only needed the first time this name is used")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        run_snapshot(VolFitterRepository(build_engine()), args.underlying, args.chain_ric)
    except UnregisteredNameError as exc:
        raise SystemExit(str(exc))
