"""Vectorized Black-76 implied volatility solver.

Jäckel-style numerical robustness: every quote is reduced to its
out-of-the-money representation via put-call parity before solving, since
the (undiscounted, normalized) Black price function is best-conditioned
there (no catastrophic cancellation against a large intrinsic value).
Solved by vectorized bisection (a guaranteed bracket) followed by a few
Halley iterations for high-precision polish. Every step is an elementwise
numpy operation across the whole input array at once — no native
extensions (no numba/cython), no per-point Python loop.

Works in reduced/normalized variables throughout:
  x = ln(F/K)                      (log-moneyness)
  y = theta * x                    (theta=+1 call, -1 put; after OTM reduction, y <= 0)
  s = sigma * sqrt(T)              (total standard deviation, what we solve for)
  beta = undiscounted_price / sqrt(F*K)   (normalized price)
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

from vol_fitter import config
from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)

_EPS = 1e-12


def _reduce_to_otm(forward_price: np.ndarray, F: np.ndarray, K: np.ndarray, is_call: np.ndarray):
    """Map every quote onto its OTM side via put-call parity. Returns (beta, y)."""
    x = np.log(F / K)
    theta = np.where(is_call, 1.0, -1.0)
    is_itm = theta * x > 0
    parity = F - K  # undiscounted call-minus-put
    price_otm = np.where(is_itm, forward_price - theta * parity, forward_price)
    theta_otm = np.where(is_itm, -theta, theta)
    y = theta_otm * x
    beta = price_otm / np.sqrt(F * K)
    return beta, y


def _reduced_price(y: np.ndarray, s: np.ndarray) -> np.ndarray:
    d1 = y / s + s / 2.0
    d2 = d1 - s
    return np.exp(y / 2.0) * norm.cdf(d1) - np.exp(-y / 2.0) * norm.cdf(d2)


def _reduced_vega(y: np.ndarray, s: np.ndarray) -> np.ndarray:
    d1 = y / s + s / 2.0
    return np.exp(y / 2.0) * norm.pdf(d1)


def _reduced_vomma(y: np.ndarray, s: np.ndarray) -> np.ndarray:
    d1 = y / s + s / 2.0
    dd1_ds = -y / s**2 + 0.5
    return -d1 * dd1_ds * _reduced_vega(y, s)


def implied_total_stdev(
    forward_price: np.ndarray,
    F: np.ndarray,
    K: np.ndarray,
    is_call: np.ndarray,
) -> np.ndarray:
    """Solve for s = sigma*sqrt(T) given undiscounted (forward-measure) prices.

    Returns NaN (rather than raising) wherever a price sits outside its
    no-arbitrage bounds, so a single bad quote doesn't abort a whole batch —
    callers should treat NaN as "could not be priced" and filter/flag it.
    """
    forward_price = np.asarray(forward_price, dtype=float)
    F = np.asarray(F, dtype=float)
    K = np.asarray(K, dtype=float)
    is_call = np.asarray(is_call, dtype=bool)

    beta, y = _reduce_to_otm(forward_price, F, K, is_call)
    ceiling = np.exp(y / 2.0)
    valid = (beta > 0) & (beta < ceiling)
    n_bad = int((~valid).sum())
    if n_bad:
        logger.warning("%d/%d quotes outside no-arbitrage bounds; returning NaN for those", n_bad, valid.size)

    lo = np.full_like(beta, config.IV_SOLVER_MIN_TOTAL_STDEV)
    hi = np.full_like(beta, config.IV_SOLVER_MAX_TOTAL_STDEV)

    for _ in range(20):
        need_expand = valid & (_reduced_price(y, hi) - beta < 0)
        if not np.any(need_expand):
            break
        hi = np.where(need_expand, hi * 2.0, hi)

    for _ in range(config.IV_SOLVER_BISECTION_ITERS):
        mid = 0.5 * (lo + hi)
        go_right = _reduced_price(y, mid) - beta < 0
        lo = np.where(go_right, mid, lo)
        hi = np.where(go_right, hi, mid)

    s = 0.5 * (lo + hi)
    for _ in range(config.IV_SOLVER_HALLEY_ITERS):
        f = _reduced_price(y, s) - beta
        fp = _reduced_vega(y, s)
        fpp = _reduced_vomma(y, s)
        denom = 2.0 * fp * fp - f * fpp
        safe_denom = np.where(np.abs(denom) > _EPS, denom, 1.0)
        halley_step = 2.0 * f * fp / safe_denom
        newton_step = f / np.maximum(fp, _EPS)
        step = np.where(np.abs(denom) > _EPS, halley_step, newton_step)
        s = s - step

    return np.where(valid, s, np.nan)
