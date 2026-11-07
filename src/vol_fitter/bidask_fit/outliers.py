"""Post-fit outlier check: tell bad quotes apart from places the model can't reach.

A candidate violates its own wall by more than cand_threshold. Look at its
neighbours (same expiry, within neighbor_width in neighbor_col, else in
normalized rank):
  - neighbours pushed onto the OPPOSITE wall (L2 mean > opp_threshold, >= 2 of
    them): the candidate is dragging the fit -> outlier
  - neighbours violating the SAME wall: the market goes where the model can't -> model_miss
  - otherwise -> isolated
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vol_fitter.bidask_fit.models import FitConfig, QuoteClass


class OutlierClassifier:
    def __init__(self, cfg: FitConfig):
        self.cfg = cfg

    def classify(self, quotes: pd.DataFrame, v_ask: np.ndarray, v_bid: np.ndarray, expiry_code: np.ndarray) -> np.ndarray:
        cfg = self.cfg
        classes = class_array(len(quotes), QuoteClass.OK)
        pos = self._positions(quotes, expiry_code)
        own = np.maximum(v_ask, v_bid)

        for i in np.flatnonzero(own > cfg.cand_threshold):
            nb = (expiry_code == expiry_code[i]) & (np.abs(pos - pos[i]) <= cfg.neighbor_width)
            nb[i] = False
            if not nb.any():
                classes[i] = QuoteClass.ISOLATED.value
                continue
            same, opp = (v_ask[nb], v_bid[nb]) if v_ask[i] >= v_bid[i] else (v_bid[nb], v_ask[nb])
            if nb.sum() >= 2 and _l2_mean(opp) > cfg.opp_threshold:
                classes[i] = QuoteClass.OUTLIER.value
            elif _l2_mean(same) > cfg.opp_threshold:
                classes[i] = QuoteClass.MODEL_MISS.value
            else:
                classes[i] = QuoteClass.ISOLATED.value
        return classes

    def guard_message(self, classes: np.ndarray, expiry_code: np.ndarray) -> str | None:
        """Why excluding these outliers would be unsafe, or None if it's fine."""
        is_out = classes == QuoteClass.OUTLIER.value
        n, n_out = len(classes), int(is_out.sum())
        if n_out > self.cfg.guard_total * n:
            return f"guard_total: {n_out}/{n} quotes flagged outlier (> {self.cfg.guard_total:.0%}); kept all"
        for code in np.unique(expiry_code):
            in_exp = expiry_code == code
            k = int((is_out & in_exp).sum())
            if k > self.cfg.guard_expiry * in_exp.sum():
                return f"guard_expiry: {k}/{int(in_exp.sum())} quotes of one expiry flagged outlier; kept all"
        return None

    def _positions(self, quotes: pd.DataFrame, expiry_code: np.ndarray) -> np.ndarray:
        col = self.cfg.neighbor_col
        if col in quotes.columns:
            return quotes[col].to_numpy(dtype=float)
        # No delta column: rank within expiry (row order), normalized to [0, 1].
        pos = np.zeros(len(quotes))
        for code in np.unique(expiry_code):
            idx = np.flatnonzero(expiry_code == code)
            pos[idx] = np.arange(len(idx)) / max(len(idx) - 1, 1)
        return pos


def class_array(n: int, cls: QuoteClass) -> np.ndarray:
    """Object array of plain class strings (numpy mangles str-Enum fill values)."""
    arr = np.empty(n, dtype=object)
    arr[:] = cls.value
    return arr


def _l2_mean(v: np.ndarray) -> float:
    return float(np.sqrt(np.mean(v ** 2))) if len(v) else 0.0
