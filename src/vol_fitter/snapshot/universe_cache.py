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
        cache_dir: Path = config.UNIVERSE_CACHE_DIR,
        max_age_days: int = config.UNIVERSE_MAX_AGE_DAYS,
        max_snap: int = config.MAX_SNAP,
    ):
        self.client = client
        self.chain_ric = chain_ric
        self.name = name
        self.cache_dir = cache_dir
        self.max_age = pd.Timedelta(days=max_age_days)
        self.max_snap = max_snap
        # Keyed by name and chain, so switching a name to a different chain never reuses the old universe.
        self._safe_name = re.sub(r"[^A-Za-z0-9]+", "", f"{name}_{chain_ric}") or "universe"

    def load(self) -> pd.DataFrame:
        path, ts = self._latest_file()
        universe = None
        if path is not None and pd.Timestamp.now() - ts <= self.max_age:
            universe = self._read(path, pd.Timestamp.now() - ts)
        if universe is None:
            universe = self._build()

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

    @staticmethod
    def _read(path: Path, age: pd.Timedelta) -> pd.DataFrame | None:
        """The cached universe, or None (so it gets rebuilt) when the file can't be read."""
        try:
            universe = pd.read_csv(path)
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            logger.warning("cached universe %s unreadable (%s); rebuilding from LSEG", path, exc)
            return None
        logger.info("using cached universe %s (age %s)", path, age)
        return universe

    def _build(self) -> pd.DataFrame:
        rics = self.client.expand_chain(self.chain_ric)
        logger.info("downloading universe for %s: %d RICs", self.name, len(rics))
        fields = ["STRIKE_PRC", "EXPIR_DATE", "PUTCALLIND", "UNDERLYING"]
        frames = [
            self.client.get_with_retry(rics[i : i + self.max_snap], fields)
            for i in range(0, len(rics), self.max_snap)
        ]
        universe = pd.concat(frames, ignore_index=True).dropna(subset=["STRIKE_PRC", "EXPIR_DATE"])

        path = self.cache_dir / f"universe_{self._safe_name}_{pd.Timestamp.now():{_TS_FMT}}.csv"
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            universe.to_csv(path, index=False)
            logger.info("saved universe cache %s (%d rows)", path, len(universe))
        except OSError as exc:  # the cache is an optimisation; a snapshot never fails over it
            logger.warning("could not save universe cache %s (%s); continuing without it", path, exc)
        return universe
