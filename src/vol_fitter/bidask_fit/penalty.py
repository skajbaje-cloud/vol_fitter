"""Modified exponential wall: zero with zero slope at the spread edge, exponential outside.

  wall(x) = expm1(c_w * x) - c_w * x,   x = distance outside the spread, capped at x_max

Two-sided quotes measure x in their own half-spreads (x = |u| - 1); one-sided
quotes measure it in h_min from the side that exists. Beyond x_max the wall is
flat, so a hopeless quote stops exerting any gradient (and gets reported).
"""
from __future__ import annotations

import numpy as np

from vol_fitter.bidask_fit.models import FitConfig, SpreadFrame


class ExpWallPenalty:
    def __init__(self, cfg: FitConfig):
        self.cfg = cfg

    @staticmethod
    def u(sig: np.ndarray, spread: SpreadFrame) -> np.ndarray:
        """Spread units; NaN for one-sided quotes (they have no mid)."""
        return (sig - spread.mid) / spread.h

    def violations(self, sig: np.ndarray, spread: SpreadFrame) -> tuple[np.ndarray, np.ndarray]:
        """(v_ask, v_bid) >= 0: distance past the ask / below the bid.

        Two-sided quotes in their own half-spreads, one-sided ones in h_min.
        """
        u = self.u(sig, spread)
        two, ao, bo = spread.two_sided, spread.ask_only, spread.bid_only
        v_ask = np.zeros_like(sig)
        v_bid = np.zeros_like(sig)
        v_ask[two] = np.maximum(u[two] - 1.0, 0.0)
        v_bid[two] = np.maximum(-u[two] - 1.0, 0.0)
        v_ask[ao] = np.maximum((sig[ao] - spread.ask_iv[ao]) / self.cfg.h_min, 0.0)
        v_bid[bo] = np.maximum((spread.bid_iv[bo] - sig[bo]) / self.cfg.h_min, 0.0)
        return v_ask, v_bid

    def raw_x(self, sig: np.ndarray, spread: SpreadFrame) -> np.ndarray:
        """Uncapped distance outside the spread; only one of v_ask/v_bid can be non-zero."""
        v_ask, v_bid = self.violations(sig, spread)
        return v_ask + v_bid

    def wall(self, raw_x: np.ndarray) -> np.ndarray:
        x = np.minimum(raw_x, self.cfg.x_max)
        cx = self.cfg.c_w * x
        return np.expm1(cx) - cx
