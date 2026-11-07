"""Per-quote diagnostics table and inside-the-spread statistics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from vol_fitter.bidask_fit.models import FitConfig, SpreadFrame
from vol_fitter.bidask_fit.penalty import ExpWallPenalty


class FitReporter:
    def __init__(self, cfg: FitConfig, penalty: ExpWallPenalty):
        self.cfg = cfg
        self.penalty = penalty

    def quote_table(self, quotes: pd.DataFrame, sig: np.ndarray, spread: SpreadFrame) -> pd.DataFrame:
        v_ask, v_bid = self.penalty.violations(sig, spread)
        x = v_ask + v_bid
        return pd.DataFrame(
            {
                "expiry": quotes["expiry"].to_numpy(),
                "model_iv": sig,
                "u": self.penalty.u(sig, spread),
                "v_ask": v_ask,
                "v_bid": v_bid,
                "x_capped": x > self.cfg.x_max,
                "inside": x <= self.cfg.inside_tol,
            },
            index=quotes.index,
        )

    @staticmethod
    def pct_inside(table: pd.DataFrame, used: np.ndarray) -> tuple[float, dict]:
        t = table[used]
        if t.empty:
            return 0.0, {}
        by_expiry = t.groupby("expiry")["inside"].mean().to_dict()
        return float(t["inside"].mean()), {k: float(v) for k, v in by_expiry.items()}
