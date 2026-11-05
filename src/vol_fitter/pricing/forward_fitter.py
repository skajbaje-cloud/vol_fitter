"""Per-expiry forward price and discount factor from put-call parity.

Two-stage, both LAD (robust to outliers), per the design decision:
  1. Forward F: LAD line fit of (mid_call - mid_put) vs strike, restricted
     to a narrow near-the-money band (wings add noise, not information,
     about where the money point is).
  2. Discount factor DF: with F fixed from stage 1, LAD slope-through-origin
     fit of (mid_call - mid_put) vs (F - strike), using the FULL strike
     range including wings (wings give the leverage a stable slope needs).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vol_fitter import config
from vol_fitter.logging_setup import get_logger
from vol_fitter.pricing.models import ForwardResult
from vol_fitter.pricing.robust_regression import lad_line_fit, lad_slope_through_origin

logger = get_logger(__name__)

_EPS = 1e-12


class ForwardFitter:
    def __init__(self, moneyness_band: float | None = config.FORWARD_MONEYNESS_BAND):
        self.moneyness_band = moneyness_band

    def fit_all(self, quotes: pd.DataFrame) -> list[ForwardResult]:
        results = []
        for expiry_date, group in quotes.groupby("expiry_date"):
            result = self._fit_one(expiry_date, group)
            if result is not None:
                results.append(result)
        return results

    def _fit_one(self, expiry_date, group: pd.DataFrame) -> ForwardResult | None:
        merged = self._merge_calls_puts(group)
        if len(merged) < 2:
            logger.warning("expiry %s: only %d strikes with both call+put quotes, skipping", expiry_date, len(merged))
            return None

        K = merged["strike"].to_numpy()
        y = merged["mid_diff"].to_numpy()
        weights = merged["weight"].to_numpy()

        F0 = K[np.argmin(np.abs(y))]
        band_mask = self._band_mask(K, F0)
        if band_mask.sum() < 2:
            logger.warning("expiry %s: moneyness band too narrow, using all strikes for F", expiry_date)
            band_mask = np.ones_like(K, dtype=bool)

        intercept, slope, resid1 = lad_line_fit(K[band_mask], y[band_mask], weights[band_mask])
        if abs(slope) < _EPS:
            logger.warning("expiry %s: degenerate forward-stage slope, skipping", expiry_date)
            return None
        forward = -intercept / slope

        x2 = forward - K
        df_slope, resid2 = lad_slope_through_origin(x2, y, weights)

        T = float(group["T"].iloc[0])
        return ForwardResult(
            expiry_date=expiry_date,
            T=T,
            forward=float(forward),
            discount_factor=float(df_slope),
            n_strikes_forward=int(band_mask.sum()),
            n_strikes_df=int(len(merged)),
            forward_fit_resid=resid1,
            df_fit_resid=resid2,
        )

    def _band_mask(self, K: np.ndarray, F0: float) -> np.ndarray:
        if self.moneyness_band is None:
            return np.ones_like(K, dtype=bool)
        return np.abs(np.log(K / F0)) <= self.moneyness_band

    @staticmethod
    def _merge_calls_puts(group: pd.DataFrame) -> pd.DataFrame:
        calls = group[group["is_call"]][["strike", "bid", "ask"]]
        puts = group[~group["is_call"]][["strike", "bid", "ask"]]
        merged = calls.merge(puts, on="strike", suffixes=("_c", "_p"))
        merged = merged.dropna(subset=["bid_c", "ask_c", "bid_p", "ask_p"])
        mid_c = 0.5 * (merged["bid_c"] + merged["ask_c"])
        mid_p = 0.5 * (merged["bid_p"] + merged["ask_p"])
        merged["mid_diff"] = mid_c - mid_p
        spread = (merged["ask_c"] - merged["bid_c"]) + (merged["ask_p"] - merged["bid_p"])
        merged["weight"] = 1.0 / np.maximum(spread, _EPS)
        return merged
