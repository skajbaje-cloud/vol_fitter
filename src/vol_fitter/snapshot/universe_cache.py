"""Timestamped CSV cache of a chain's strike/expiry/put-call universe.

Rebuilt from LSEG whenever missing or older than max_age_days; otherwise
loaded straight from disk, since the universe (which strikes/expiries
exist) changes far less often than prices do.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

import pandas as pd

from vol_fitter import config
from vol_fitter.logging_setup import get_logger
from vol_fitter.snapshot.lseg_client import LsegClient

logger = get_logger(__name__)

_TS_FMT = "%Y%m%d_%H%M"


class UniverseCache:
    def __init__(
        self,
        client: LsegClient,
        chain_ric: str,
        name: str,
        cache_dir: Path = Path("."),
        max_age_days: int = config.UNIVERSE_MAX_AGE_DAYS,
        max_snap: int = config.MAX_SNAP,
    ):
        self.client = client
        self.chain_ric = chain_ric
        self.name = name
        self.cache_dir = cache_dir
        self.max_age = pd.Timedelta(days=max_age_days)
        self.max_snap = max_snap
        self._safe_name = re.sub(r"[^A-Za-z0-9]+", "", name) or "universe"

    def load(self) -> pd.DataFrame:
        path, ts = self._latest_file()
        if path is None or pd.Timestamp.now() - ts > self.max_age:
            universe = self._build()
        else:
            logger.info("using cached universe %s (age %s)", path, pd.Timestamp.now() - ts)
            universe = pd.read_csv(path)

        universe["EXPIR_DATE"] = pd.to_datetime(universe["EXPIR_DATE"])
        universe["is_call"] = universe["PUTCALLIND"].astype(str).str.upper().str.startswith("C")
        today = pd.Timestamp.today().normalize()
        universe = universe[universe["EXPIR_DATE"] >= today].copy()
        universe["T"] = (universe["EXPIR_DATE"] - today).dt.days.clip(lower=1) / 365.0
        return universe

    def _latest_file(self) -> tuple[Path | None, pd.Timestamp | None]:
        pattern = str(self.cache_dir / f"universe_{self._safe_name}_*.csv")
        files = sorted(glob.glob(pattern))
        if not files:
            return None, None
        path = Path(files[-1])
        ts_str = path.stem[len(f"universe_{self._safe_name}_"):]
        return path, pd.to_datetime(ts_str, format=_TS_FMT)

    def _build(self) -> pd.DataFrame:
        rics = self.client.expand_chain(self.chain_ric)
        logger.info("downloading universe for %s: %d RICs", self.name, len(rics))
        fields = ["STRIKE_PRC", "EXPIR_DATE", "PUTCALLIND"]
        frames = [
            self.client.get_with_retry(rics[i : i + self.max_snap], fields)
            for i in range(0, len(rics), self.max_snap)
        ]
        universe = pd.concat(frames, ignore_index=True).dropna(subset=["STRIKE_PRC", "EXPIR_DATE"])

        path = self.cache_dir / f"universe_{self._safe_name}_{pd.Timestamp.now():{_TS_FMT}}.csv"
        universe.to_csv(path, index=False)
        logger.info("saved universe cache %s (%d rows)", path, len(universe))
        return universe
