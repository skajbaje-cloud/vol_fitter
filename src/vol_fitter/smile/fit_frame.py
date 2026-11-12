"""raw_quotes + per-expiry DF -> the frame the smile model and bidask_fit read.

Every quote is kept (calls and puts, one-sided too): the fitter only needs the
model above each bid and below each ask, so ITM and one-sided quotes still add
information. The model coordinate is the forward call-equivalent delta:

  stored delta is Black-76 on the discounted price: calls DF*N(d1), puts -DF*N(-d1)
  forward call delta = delta/DF (calls), 1 + delta/DF (puts)
  delta used = mean of the bid-side and ask-side values (whichever exist)
  z = Phi^-1(delta), the axis the smile model is written on
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)

FRAME_COLUMNS = ["instrument", "expiry", "T", "strike", "is_call", "bid_iv", "ask_iv",
                 "delta", "z", "otm_delta"]


class FitFrameBuilder:
    def build(self, quotes: pd.DataFrame, maturities: pd.DataFrame) -> pd.DataFrame:
        df = quotes.merge(maturities[["expiry_date", "discount_factor"]], on="expiry_date", how="inner")
        lost = len(quotes) - len(df)
        if lost:
            logger.warning("%d quotes have no discount factor for their expiry; skipped", lost)

        is_call = df["is_call"].astype(bool).to_numpy()
        delta = self.forward_call_delta(df, df["discount_factor"].to_numpy(dtype=float))

        out = pd.DataFrame({
            "instrument": df["instrument"].to_numpy(),
            "expiry": df["expiry_date"].to_numpy(),
            "T": df["T"].to_numpy(dtype=float),
            "strike": df["strike"].to_numpy(dtype=float),
            "is_call": is_call,
            "bid_iv": df["bid_iv"].to_numpy(dtype=float),
            "ask_iv": df["ask_iv"].to_numpy(dtype=float),
            "delta": delta,
        })
        out["z"] = norm.ppf(np.clip(out["delta"], 1e-4, 1 - 1e-4))   # the smile model's axis
        out["otm_delta"] = np.minimum(out["delta"], 1.0 - out["delta"])

        no_delta = ~np.isfinite(out["delta"].to_numpy())
        if no_delta.any():
            logger.info("%d quotes have neither bid nor ask delta; left out of the fit frame", int(no_delta.sum()))
        return out[~no_delta].reset_index(drop=True)[FRAME_COLUMNS]

    def forward_call_delta(self, quotes: pd.DataFrame, DF) -> np.ndarray:
        """Row-aligned forward call-equivalent delta (mean of bid/ask sides); NaN if neither side has one."""
        DF = np.broadcast_to(np.asarray(DF, dtype=float), len(quotes))
        is_call = quotes["is_call"].astype(bool).to_numpy()
        sides = np.vstack([self._call_equivalent(quotes[col].to_numpy(dtype=float), DF, is_call)
                           for col in ("bid_delta", "ask_delta")])
        n_sides = np.isfinite(sides).sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(n_sides > 0, np.nansum(sides, axis=0) / n_sides, np.nan)

    @staticmethod
    def _call_equivalent(delta: np.ndarray, DF: np.ndarray, is_call: np.ndarray) -> np.ndarray:
        fwd = delta / DF
        return np.where(is_call, fwd, 1.0 + fwd)
