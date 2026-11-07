"""Turns quote vols into spread geometry (mid, half-spread, which walls bind)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vol_fitter.bidask_fit.models import FitConfig, SpreadFrame
from vol_fitter.bidask_fit.weights import WeightBuilder


class SpreadBuilder:
    def __init__(self, cfg: FitConfig):
        self.cfg = cfg
        self.weights = WeightBuilder(cfg)

    @staticmethod
    def usable(quotes: pd.DataFrame) -> np.ndarray:
        """Quotes with at least one side -- everything else can't constrain a fit."""
        bid = quotes["bid_iv"].to_numpy(dtype=float)
        ask = quotes["ask_iv"].to_numpy(dtype=float)
        return np.isfinite(bid) | np.isfinite(ask)

    def build(self, quotes: pd.DataFrame) -> SpreadFrame:
        bid = quotes["bid_iv"].to_numpy(dtype=float)
        ask = quotes["ask_iv"].to_numpy(dtype=float)
        has_bid, has_ask = np.isfinite(bid), np.isfinite(ask)
        two = has_bid & has_ask

        with np.errstate(invalid="ignore"):
            mid = np.where(two, 0.5 * (bid + ask), np.nan)
            h = np.where(two, np.maximum(0.5 * (ask - bid), self.cfg.h_min), self.cfg.h_min)

        expiry_code = pd.factorize(quotes["expiry"])[0]
        return SpreadFrame(
            bid_iv=bid,
            ask_iv=ask,
            mid=mid,
            h=h,
            two_sided=two,
            ask_only=has_ask & ~has_bid,
            bid_only=has_bid & ~has_ask,
            weight=self.weights.build(quotes, expiry_code),
            expiry_code=expiry_code,
        )
