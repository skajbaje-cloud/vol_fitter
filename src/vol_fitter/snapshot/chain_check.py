"""Expand a candidate chain and summarise what's in it.

Expansion is the slow part of a first snapshot (minutes for .SPX), so this goes
through UniverseCache: a check warms the cache and the first snapshot reuses it.
"""
from __future__ import annotations

import time

import pandas as pd

from vol_fitter.logging_setup import get_logger
from vol_fitter.snapshot.lseg_client import LsegClient
from vol_fitter.snapshot.models import ChainCheck
from vol_fitter.snapshot.name_lookup import ric_root
from vol_fitter.snapshot.universe_cache import UniverseCache

logger = get_logger(__name__)


class ChainChecker:
    def __init__(self, client: LsegClient):
        self.client = client

    def check(self, name: str, chain_ric: str) -> ChainCheck:
        t0 = time.time()
        universe = UniverseCache(self.client, chain_ric, name=name).load()
        return summarise(name, chain_ric, universe, time.time() - t0)


def summarise(name: str, chain_ric: str, universe: pd.DataFrame, duration_sec: float = 0.0) -> ChainCheck:
    expiries = pd.to_datetime(universe["EXPIR_DATE"]).dt.date if len(universe) else pd.Series(dtype=object)
    strikes = pd.to_numeric(universe.get("STRIKE_PRC", pd.Series(dtype=float)), errors="coerce")
    match = None
    if "UNDERLYING" in universe.columns and universe["UNDERLYING"].notna().any():
        reported = universe["UNDERLYING"].dropna().astype(str)
        match = float(reported.isin({name, ric_root(name)}).mean())
    check = ChainCheck(
        name=name, chain_ric=chain_ric, n_options=len(universe), n_expiries=int(expiries.nunique()),
        first_expiry=expiries.min() if len(expiries) else None, last_expiry=expiries.max() if len(expiries) else None,
        strike_min=float(strikes.min()) if strikes.notna().any() else None,
        strike_max=float(strikes.max()) if strikes.notna().any() else None,
        underlying_match=match, duration_sec=duration_sec,
    )
    logger.info("chain %s for %s: %d options, %d expiries, underlying match %s",
                chain_ric, name, check.n_options, check.n_expiries, match)
    return check
