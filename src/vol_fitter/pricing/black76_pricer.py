"""Black-76 pricer: price, implied vol, and Greeks, scalar or vectorized.

Combines black76_formulas (closed-form price/greeks) with jackel_iv
(implied-vol inversion) behind one interface, and provides the bulk
price_quotes() entry point that joins a snapshot's raw quotes with their
per-expiry ForwardResult and prices everything in one vectorized pass.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vol_fitter.logging_setup import get_logger
from vol_fitter.pricing import black76_formulas, jackel_iv
from vol_fitter.pricing.models import ForwardResult

logger = get_logger(__name__)

_GREEK_NAMES = ("delta", "gamma", "vega", "theta", "rho")


class Black76Pricer:
    @staticmethod
    def price(F, K, T, sigma, DF, is_call) -> np.ndarray:
        return black76_formulas.price(F, K, T, sigma, DF, is_call)

    @staticmethod
    def greeks(F, K, T, sigma, DF, is_call) -> dict[str, np.ndarray]:
        return black76_formulas.greeks(F, K, T, sigma, DF, is_call)

    @staticmethod
    def implied_vol(price, F, K, T, DF, is_call) -> np.ndarray:
        price = np.asarray(price, dtype=float)
        DF = np.asarray(DF, dtype=float)
        T = np.asarray(T, dtype=float)
        forward_price = price / DF
        s = jackel_iv.implied_total_stdev(forward_price, F, K, is_call)
        return s / np.sqrt(T)

    def price_quotes(self, quotes: pd.DataFrame, forwards: list[ForwardResult]) -> pd.DataFrame:
        """Join quotes to their expiry's forward/DF and price bid+ask in bulk."""
        if not forwards:
            logger.warning("no forward results supplied; returning quotes unpriced")
            return quotes.copy()

        fwd_df = pd.DataFrame(
            {
                "expiry_date": [f.expiry_date for f in forwards],
                "T": [f.T for f in forwards],
                "forward": [f.forward for f in forwards],
                "discount_factor": [f.discount_factor for f in forwards],
            }
        )
        df = quotes.drop(columns=["T"], errors="ignore").merge(fwd_df, on="expiry_date", how="inner")
        dropped = len(quotes) - len(df)
        if dropped:
            logger.warning("%d/%d quotes dropped: no forward result for their expiry", dropped, len(quotes))

        F = df["forward"].to_numpy()
        K = df["strike"].to_numpy()
        T = df["T"].to_numpy()
        DF = df["discount_factor"].to_numpy()
        is_call = df["is_call"].to_numpy()

        df["bid_iv"] = self.implied_vol(df["bid"].to_numpy(), F, K, T, DF, is_call)
        df["ask_iv"] = self.implied_vol(df["ask"].to_numpy(), F, K, T, DF, is_call)

        bid_greeks = self.greeks(F, K, T, df["bid_iv"].to_numpy(), DF, is_call)
        ask_greeks = self.greeks(F, K, T, df["ask_iv"].to_numpy(), DF, is_call)
        for name in _GREEK_NAMES:
            df[f"bid_{name}"] = bid_greeks[name]
            df[f"ask_{name}"] = ask_greeks[name]

        n_unpriced = int(df["bid_iv"].isna().sum() + df["ask_iv"].isna().sum())
        if n_unpriced:
            logger.warning("%d bid/ask sides could not be assigned an implied vol", n_unpriced)

        return df
