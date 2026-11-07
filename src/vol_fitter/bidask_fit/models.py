"""Plain data holders for the bid-ask fitter (no logic here).

Spread units: mid = (bid+ask)/2, h = max((ask-bid)/2, h_min), u = (sig-mid)/h,
so the bid sits at u = -1 and the ask at u = +1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd


class FitStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"


class QuoteClass(str, Enum):
    OK = "ok"
    OUTLIER = "outlier"            # neighbours are pushed onto the opposite wall -> bad quote
    MODEL_MISS = "model_miss"      # neighbours violate the same wall -> model can't reach the market
    ISOLATED = "isolated"          # big violation, neighbours unaffected
    DROPPED = "dropped"            # neither bid nor ask vol: never entered the fit


@dataclass(frozen=True)
class FitConfig:
    # wall / floor
    c_w: float = 2.0
    x_max: float = 5.0
    eps: float = 0.01
    h_min: float = 0.0025
    # previous-fit anchor (parameter space): r = sqrt(lam_a) * (p - p_prev) / anchor_scale
    lam_a: float = 0.0
    anchor_scale: tuple[float, ...] | None = None   # None = ones
    anchor_guard: bool = True        # anchored fit may not leave more quotes outside than an unanchored one
    anchor_backoff: float = 10.0     # lam_a divisor per guard retry
    anchor_max_backoffs: int = 3
    # weights
    taper: bool = False
    taper_delta: float = 0.05
    taper_col: str = "delta"
    # status / outliers
    max_outside_frac: float = 0.5
    inside_tol: float = 1e-6         # x above this counts as outside
    cand_threshold: float = 2.0
    opp_threshold: float = 0.25
    neighbor_width: float = 0.15
    neighbor_col: str = "delta"
    guard_total: float = 0.05
    guard_expiry: float = 1.0 / 3.0
    # optimizer
    max_nfev: int | None = None


DEFAULT_CFG = FitConfig()


@dataclass(frozen=True)
class SpreadFrame:
    """Per-quote spread geometry, aligned with the quotes it was built from."""
    bid_iv: np.ndarray
    ask_iv: np.ndarray
    mid: np.ndarray           # NaN unless two-sided
    h: np.ndarray             # half-spread (h_min for one-sided quotes)
    two_sided: np.ndarray     # bool
    ask_only: np.ndarray      # bool: bid missing -> only the ask wall binds
    bid_only: np.ndarray      # bool: ask missing -> only the bid wall binds
    weight: np.ndarray
    expiry_code: np.ndarray   # int, factorized expiry


@dataclass(frozen=True)
class SolveOutcome:
    """One least_squares run (internal to the fitter, kept as data for clarity)."""
    p: np.ndarray
    success: bool
    message: str
    objective: float
    anchor_lambda: float
    anchor_relaxed: bool = False


@dataclass(frozen=True)
class FitResult:
    p: np.ndarray
    status: FitStatus
    objective: float
    n_quotes: int                         # quotes used in the final fit
    pct_inside: float
    pct_inside_by_expiry: dict
    quotes: pd.DataFrame                  # per-quote table, indexed like the input quotes
    flags: list[str] = field(default_factory=list)
    p_first: np.ndarray | None = None     # set only when a refit ran
    refit_delta: np.ndarray | None = None
    anchor_lambda: float = 0.0            # lambda actually used (after any guard back-off)
    anchor_relaxed: bool = False          # guard dropped the anchor entirely
    cfg: FitConfig = DEFAULT_CFG
