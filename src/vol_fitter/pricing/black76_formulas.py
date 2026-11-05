"""Closed-form, vectorized Black-76 price and Greeks.

Standard formulas (not Jäckel-related — that machinery is only needed for
the inverse problem, implied vol; see jackel_iv.py). The discount factor DF
is converted to an equivalent continuously-compounded rate
r = -ln(DF)/T per expiry for the theta/rho formulas; d1/d2 themselves don't
depend on r since F is already the forward.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm


def _d1_d2(F: np.ndarray, K: np.ndarray, T: np.ndarray, sigma: np.ndarray):
    total_stdev = sigma * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sigma * sigma * T) / total_stdev
    d2 = d1 - total_stdev
    return d1, d2


def forward_price(F: np.ndarray, K: np.ndarray, T: np.ndarray, sigma: np.ndarray, is_call: np.ndarray) -> np.ndarray:
    """Undiscounted price (i.e. price/DF)."""
    d1, d2 = _d1_d2(F, K, T, sigma)
    call = F * norm.cdf(d1) - K * norm.cdf(d2)
    put = K * norm.cdf(-d2) - F * norm.cdf(-d1)
    return np.where(is_call, call, put)


def price(F: np.ndarray, K: np.ndarray, T: np.ndarray, sigma: np.ndarray, DF: np.ndarray, is_call: np.ndarray) -> np.ndarray:
    return DF * forward_price(F, K, T, sigma, is_call)


def greeks(
    F: np.ndarray,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    DF: np.ndarray,
    is_call: np.ndarray,
) -> dict[str, np.ndarray]:
    F, K, T, sigma, DF = (np.asarray(a, dtype=float) for a in (F, K, T, sigma, DF))
    is_call = np.asarray(is_call, dtype=bool)
    d1, d2 = _d1_d2(F, K, T, sigma)
    r = -np.log(DF) / T

    disc_price = price(F, K, T, sigma, DF, is_call)
    delta = np.where(is_call, DF * norm.cdf(d1), -DF * norm.cdf(-d1))
    gamma = DF * norm.pdf(d1) / (F * sigma * np.sqrt(T))
    vega = DF * F * norm.pdf(d1) * np.sqrt(T)
    theta = r * disc_price - DF * F * norm.pdf(d1) * sigma / (2.0 * np.sqrt(T))
    rho = -T * disc_price

    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho}
