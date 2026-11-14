"""Quotes -> the bid/ask constraint points of the bid-ask spline study.

Axis: z = Phi^-1(1 - call delta) = -d1, which increases with strike. A quote's z depends on
the vol it is evaluated at, so its bid and ask IVs sit at different z:

    z(sigma; k) = k / (sigma*sqrt(T)) - sigma*sqrt(T)/2,    k = ln(K/F)

The curve passes between bid and ask exactly when s(z_bid) >= iv_bid and s(z_ask) <= iv_ask.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vol_fitter.logging_setup import get_logger
from vol_fitter.smile.models import SplineConfig, SplinePoints

logger = get_logger(__name__)


def z_of(sigma, log_moneyness, T: float) -> np.ndarray:
    """Phi^-1(1 - forward call delta) for vol `sigma` at k = ln(K/F)."""
    sd = np.asarray(sigma, dtype=float) * np.sqrt(T)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.asarray(log_moneyness, dtype=float) / sd - 0.5 * sd


class SplinePointBuilder:
    def __init__(self, cfg: SplineConfig = SplineConfig()):
        self.cfg = cfg

    def build(self, quotes: pd.DataFrame, forward: float, T: float) -> SplinePoints:
        """quotes: one expiry's raw_quotes rows (strike, is_call, bid_iv, ask_iv)."""
        k = np.log(quotes["strike"].to_numpy(dtype=float) / forward)
        iv_bid = self._positive(quotes["bid_iv"])
        iv_ask = self._positive(quotes["ask_iv"])
        # Placeholder markets (0.03 bid / 200 ask on illiquid expiries) say nothing about the smile.
        wide = (iv_ask - iv_bid) > self.cfg.max_iv_spread
        iv_bid[wide], iv_ask[wide] = np.nan, np.nan
        z_bid, z_ask = z_of(iv_bid, k, T), z_of(iv_ask, k, T)

        # A bound beyond max_abs_z (deltas below ~3e-5) is dropped; its partner may stay.
        far_bid = ~(np.abs(z_bid) <= self.cfg.max_abs_z)
        far_ask = ~(np.abs(z_ask) <= self.cfg.max_abs_z)
        iv_bid[far_bid], z_bid[far_bid] = np.nan, np.nan
        iv_ask[far_ask], z_ask[far_ask] = np.nan, np.nan

        keep = np.isfinite(iv_bid) | np.isfinite(iv_ask)
        if (~keep).any():
            logger.debug("%d quotes give no bound (no IV, or beyond |z| %.1f)", int((~keep).sum()), self.cfg.max_abs_z)
        return SplinePoints(
            strike=quotes["strike"].to_numpy(dtype=float)[keep],
            is_call=quotes["is_call"].astype(bool).to_numpy()[keep],
            z_bid=z_bid[keep], iv_bid=iv_bid[keep], z_ask=z_ask[keep], iv_ask=iv_ask[keep],
        )

    @staticmethod
    def _positive(values: pd.Series) -> np.ndarray:
        v = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float).copy()
        v[~(v > 0)] = np.nan
        return v
