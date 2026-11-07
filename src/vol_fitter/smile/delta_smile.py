"""Per-expiry smile in forward-delta space, on the normal-quantile axis z = Phi^-1(call delta).

  sigma(z) = atm + skew * z + kappa_put * (z+)^2 + kappa_call * (z-)^2
  z+ = max(z, 0) (put side: call delta > 0.5),  z- = max(-z, 0) (call side)

z is a monotone relabelling of delta (it equals d1), so the model still lives in
delta space; it stretches the wings, where vol changes fastest per unit delta.
atm and skew are the vol and slope at z = 0 (50 delta). Each kappa is the vol added
above the skew line at z = +/-1 (about the 16-delta put / call); the wing keeps
growing quadratically beyond. Local convexity is 2*kappa on each side.
Callable as model(p, quotes) for bidask_fit, reading only quotes["delta"].
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from vol_fitter.logging_setup import get_logger
from vol_fitter.smile.models import SmileModelConfig

logger = get_logger(__name__)

_ATM_BAND = 0.25      # |z| band used to guess atm
_SKEW_BAND = 0.70     # |z| band used to guess skew


class DeltaSmileModel:
    n_params = 4

    def __init__(self, cfg: SmileModelConfig = SmileModelConfig()):
        self.cfg = cfg
        self._grid_z = self.z_of(np.linspace(0.0, 1.0, cfg.grid_points))

    def z_of(self, delta) -> np.ndarray:
        c = self.cfg.delta_clip
        return norm.ppf(np.clip(np.asarray(delta, dtype=float), c, 1.0 - c))

    def vol_at_z(self, p, z: np.ndarray) -> np.ndarray:
        atm, skew, k_put, k_call = p
        z = np.asarray(z, dtype=float)
        return atm + skew * z + k_put * np.maximum(z, 0.0) ** 2 + k_call * np.maximum(-z, 0.0) ** 2

    def vol_at_delta(self, p, delta) -> np.ndarray:
        return self.vol_at_z(p, self.z_of(delta))

    def __call__(self, p, quotes: pd.DataFrame) -> np.ndarray:
        return self.vol_at_delta(p, quotes["delta"].to_numpy(dtype=float))

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return np.array(self.cfg.lower, dtype=float), np.array(self.cfg.upper, dtype=float)

    def positivity_penalty(self, p) -> np.ndarray:
        """Extra residuals for bidask_fit's model_penalty hook: zero while vol >= floor everywhere."""
        short = np.maximum(self.cfg.vol_floor - self.vol_at_z(p, self._grid_z), 0.0)
        return np.sqrt(self.cfg.floor_penalty_weight) * short

    def initial_guess(self, quotes: pd.DataFrame) -> np.ndarray:
        """atm from near-the-money mids, skew from a line through |z| < 0.7, no wings."""
        z = self.z_of(quotes["delta"].to_numpy(dtype=float))
        mid = 0.5 * (quotes["bid_iv"].to_numpy(dtype=float) + quotes["ask_iv"].to_numpy(dtype=float))
        ok = np.isfinite(mid) & np.isfinite(z)
        if not ok.any():
            mid = quotes["ask_iv"].to_numpy(dtype=float)
            ok = np.isfinite(mid) & np.isfinite(z)
        z, mid = z[ok], mid[ok]

        near = np.abs(z) < _ATM_BAND
        atm = float(np.median(mid[near])) if near.any() else float(mid[np.argmin(np.abs(z))])
        band = np.abs(z) < _SKEW_BAND
        skew = float(np.polyfit(z[band], mid[band], 1)[0]) if band.sum() >= 3 else 0.0

        lb, ub = self.bounds()
        return np.clip(np.array([atm, skew, 0.0, 0.0]), lb, ub)
