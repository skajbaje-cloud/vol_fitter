"""Orchestrates one point-in-time snapshot: universe -> std-dev window -> snap.

Window is z = ln(K/S) / (vol * sqrt(T)); keeps calls/puts within their own
configured z-range around spot, then caps to the largest safe batch size by
dropping whole expiries from the back (never splitting one expiry's strikes
across batches).
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from vol_fitter import config
from vol_fitter.logging_setup import get_logger
from vol_fitter.snapshot.lseg_client import LsegClient
from vol_fitter.snapshot.models import SnapshotMeta
from vol_fitter.snapshot.universe_cache import UniverseCache

logger = get_logger(__name__)

_QUOTE_COLUMNS = ["instrument", "strike", "expiry_date", "T", "is_call", "bid", "ask"]


class SnapshotService:
    def __init__(
        self,
        client: LsegClient,
        universe_cache: UniverseCache,
        underlying: str,
        call_sd_window: tuple[float, float] = config.CALL_SD_WINDOW,
        put_sd_window: tuple[float, float] = config.PUT_SD_WINDOW,
        max_snap: int = config.MAX_SNAP,
        vol_field: str = config.VOL_FIELD,
    ):
        self.client = client
        self.universe_cache = universe_cache
        self.underlying = underlying
        self.call_sd_window = call_sd_window
        self.put_sd_window = put_sd_window
        self.max_snap = max_snap
        self.vol_field = vol_field

    def snap(self) -> tuple[pd.DataFrame, SnapshotMeta]:
        t0 = time.time()
        universe = self.universe_cache.load()
        spot0, vol = self._spot_and_vol()
        windowed = self._in_window(universe, spot0, vol)
        capped = self._cap(windowed)
        logger.info(
            "spot %.2f, vol %.1f%%: universe %d -> window %d RICs, %d expiries",
            spot0, vol * 100, len(universe), len(capped), capped["EXPIR_DATE"].nunique(),
        )

        quotes = self.client.get_with_retry([self.underlying] + capped["Instrument"].tolist(), ["BID", "ASK", "TRDPRC_1"])
        spot = quotes.loc[quotes["Instrument"] == self.underlying, "TRDPRC_1"].iloc[0]
        df = capped.merge(quotes[["Instrument", "BID", "ASK"]], on="Instrument")

        quotes_df = df.rename(
            columns={"Instrument": "instrument", "STRIKE_PRC": "strike", "EXPIR_DATE": "expiry_date", "BID": "bid", "ASK": "ask"}
        )[_QUOTE_COLUMNS].copy()
        quotes_df["expiry_date"] = pd.to_datetime(quotes_df["expiry_date"]).dt.date

        meta = SnapshotMeta(
            name=self.underlying,
            snapshot_ts=pd.Timestamp.now(),
            spot=float(spot),
            universe_size=len(universe),
            window_size=len(quotes_df),
            snap_duration_sec=time.time() - t0,
            status="ok",
        )
        return quotes_df, meta

    def _spot_and_vol(self) -> tuple[float, float]:
        # One field for a last price, one for a realized-vol content field --
        # both requestable directly on the underlying's own RIC, so this
        # works the same way for an index, an ETF, or a single stock.
        # TR.* content fields come back under a human-readable display
        # column (e.g. "Volatility - 40 days"), not their field code, unlike
        # legacy real-time fields like TRDPRC_1 -- so find it by elimination
        # rather than assuming the column is literally named self.vol_field.
        d = self.client.get_with_retry([self.underlying], ["TRDPRC_1", self.vol_field])
        vol_col = next(c for c in d.columns if c not in ("Instrument", "TRDPRC_1"))
        spot, vol = d.loc[0, "TRDPRC_1"], d.loc[0, vol_col]
        if pd.isna(spot) or pd.isna(vol):
            raise RuntimeError(f"missing spot ({spot}) or vol ({vol}) for {self.underlying}")
        # TR.Volatility40D comes back as a percentage (e.g. 18.2 for 18.2%).
        return float(spot), float(vol) / 100.0

    def _in_window(self, universe: pd.DataFrame, spot: float, vol: float) -> pd.DataFrame:
        z = np.log(universe["STRIKE_PRC"] / spot) / (vol * np.sqrt(universe["T"]))
        lo = np.where(universe["is_call"], self.call_sd_window[0], self.put_sd_window[0])
        hi = np.where(universe["is_call"], self.call_sd_window[1], self.put_sd_window[1])
        return universe[(z >= lo) & (z <= hi)]

    def _cap(self, windowed: pd.DataFrame) -> pd.DataFrame:
        counts = windowed.groupby("EXPIR_DATE").size().sort_index()
        keep = counts[counts.cumsum() <= self.max_snap - 1].index  # -1 for the underlying itself
        dropped = len(counts) - len(keep)
        if dropped:
            logger.warning("over %d RICs; dropped last %d expiries", self.max_snap, dropped)
        return windowed[windowed["EXPIR_DATE"].isin(keep)]
