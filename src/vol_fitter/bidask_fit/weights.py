"""Default per-quote weights: each expiry gets equal total weight."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vol_fitter.bidask_fit.models import FitConfig
from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)


class WeightBuilder:
    def __init__(self, cfg: FitConfig):
        self.cfg = cfg

    def build(self, quotes: pd.DataFrame, expiry_code: np.ndarray) -> np.ndarray:
        if "weight" in quotes.columns:
            # A user-supplied column replaces the defaults entirely.
            return quotes["weight"].to_numpy(dtype=float)

        counts = np.bincount(expiry_code)
        w = 1.0 / counts[expiry_code]

        if self.cfg.taper:
            if self.cfg.taper_col in quotes.columns:
                d = np.abs(quotes[self.cfg.taper_col].to_numpy(dtype=float))
                w = w * np.minimum(1.0, np.nan_to_num(d, nan=1.0) / self.cfg.taper_delta)
            else:
                logger.warning("taper requested but column %r is missing; no taper applied", self.cfg.taper_col)
        return w
