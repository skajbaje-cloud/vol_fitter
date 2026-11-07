"""Residual vector for scipy.optimize.least_squares.

  r_wall   = sqrt(w * wall)                       every usable quote
  r_floor  = sqrt(w * eps) * u                    two-sided quotes only (uniqueness inside the spread)
  r_anchor = sqrt(lam) * (p - p_prev) / scale     only with an anchor and lam > 0
  r_model  = model_penalty(p)                     appended as-is, if supplied

Wall and floor are separate residuals (not sqrt of their sum), so least_squares
sees each one's own Jacobian.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from vol_fitter.bidask_fit.models import FitConfig, SpreadFrame
from vol_fitter.bidask_fit.penalty import ExpWallPenalty

ModelFn = Callable[[np.ndarray, pd.DataFrame], np.ndarray]
PenaltyFn = Callable[[np.ndarray], np.ndarray]

# A model returning NaN/inf would make least_squares abort; treat it as "very wrong" instead.
_NONFINITE_VOL = 10.0


class ResidualFunction:
    def __init__(
        self,
        model: ModelFn,
        quotes: pd.DataFrame,
        spread: SpreadFrame,
        penalty: ExpWallPenalty,
        cfg: FitConfig,
        p_prev: np.ndarray | None = None,
        lam: float = 0.0,
        model_penalty: PenaltyFn | None = None,
    ):
        self.model = model
        self.quotes = quotes
        self.spread = spread
        self.penalty = penalty
        self.cfg = cfg
        self.model_penalty = model_penalty
        self.anchored = p_prev is not None and lam > 0
        if self.anchored:
            scale = np.ones_like(p_prev) if cfg.anchor_scale is None else np.asarray(cfg.anchor_scale, float)
            self.p_prev = np.asarray(p_prev, float)
            self.anchor_coef = np.sqrt(lam) / scale
        self.sqrt_w = np.sqrt(spread.weight)
        self.sqrt_w_eps = np.sqrt(spread.weight[spread.two_sided] * cfg.eps)

    def model_vols(self, p: np.ndarray) -> np.ndarray:
        sig = np.asarray(self.model(p, self.quotes), dtype=float)
        return np.where(np.isfinite(sig), sig, _NONFINITE_VOL)

    def __call__(self, p: np.ndarray) -> np.ndarray:
        sig = self.model_vols(p)
        wall = self.penalty.wall(self.penalty.raw_x(sig, self.spread))
        parts = [self.sqrt_w * np.sqrt(np.maximum(wall, 0.0))]

        u = self.penalty.u(sig, self.spread)[self.spread.two_sided]
        parts.append(self.sqrt_w_eps * u)

        if self.anchored:
            parts.append(self.anchor_coef * (np.asarray(p, float) - self.p_prev))
        if self.model_penalty is not None:
            parts.append(np.atleast_1d(np.asarray(self.model_penalty(p), dtype=float)))
        return np.concatenate(parts)
