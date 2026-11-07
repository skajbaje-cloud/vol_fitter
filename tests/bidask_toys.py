"""Toy models and synthetic quotes for the bid-ask fitter tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

EXPIRIES = ["E1", "E2"]
TAUS = {"E1": 0.25, "E2": 1.0}
TRUE_P = np.array([0.20, -0.30, 0.22, -0.15])   # (level, slope) per expiry


class LinearSmile:
    """sig = a_e + b_e * k for each expiry e; p = [a_1, b_1, a_2, b_2, ...]."""

    def __init__(self, expiries=EXPIRIES):
        self.code = {e: i for i, e in enumerate(expiries)}

    def __call__(self, p, quotes):
        c = quotes["expiry"].map(self.code).to_numpy()
        p = np.asarray(p)
        return p[2 * c] + p[2 * c + 1] * quotes["k"].to_numpy()


class QuadraticSmile:
    """sig = a_e + b_e * k + c_e * k^2 -- a different callable, same fitter."""

    def __init__(self, expiries=EXPIRIES):
        self.code = {e: i for i, e in enumerate(expiries)}

    def __call__(self, p, quotes):
        c = quotes["expiry"].map(self.code).to_numpy()
        p, k = np.asarray(p), quotes["k"].to_numpy()
        return p[3 * c] + p[3 * c + 1] * k + p[3 * c + 2] * k ** 2


def make_quotes(vol_fn=None, n_per_expiry=30, seed=0, half_spread=(0.003, 0.008)) -> pd.DataFrame:
    """Two-sided quotes whose true vol (vol_fn(quotes), default the linear TRUE_P smile) sits inside each spread."""
    rng = np.random.default_rng(seed)
    rows = []
    for e in EXPIRIES:
        k = np.linspace(-0.4, 0.3, n_per_expiry)
        rows.append(pd.DataFrame({"expiry": e, "k": k, "tau": TAUS[e]}))
    q = pd.concat(rows, ignore_index=True)
    sig = vol_fn(q) if vol_fn else LinearSmile()(TRUE_P, q)
    h = rng.uniform(*half_spread, len(q))
    mid = sig + rng.uniform(-0.5, 0.5, len(q)) * h
    q["bid_iv"], q["ask_iv"] = mid - h, mid + h
    d1 = (-q["k"] + 0.5 * sig ** 2 * q["tau"]) / (sig * np.sqrt(q["tau"]))
    q["delta"] = norm.cdf(d1)
    return q
