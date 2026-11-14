"""Plain data holders for the delta-space smile model (no fitting logic)."""
from __future__ import annotations

from dataclasses import astuple, dataclass
from typing import ClassVar

import numpy as np

from vol_fitter import config


@dataclass(frozen=True)
class SmileParams:
    sigma_atm: float
    skew: float
    kappa_put: float
    kappa_call: float

    NAMES: ClassVar[tuple[str, ...]] = ("sigma_atm", "skew", "kappa_put", "kappa_call")

    def to_vector(self) -> np.ndarray:
        return np.array(astuple(self), dtype=float)

    @classmethod
    def from_vector(cls, v) -> "SmileParams":
        return cls(*(float(x) for x in v))


@dataclass(frozen=True)
class SmileModelConfig:
    lower: tuple[float, ...] = config.SMILE_LOWER
    upper: tuple[float, ...] = config.SMILE_UPPER
    vol_floor: float = config.SMILE_VOL_FLOOR
    floor_penalty_weight: float = 100.0
    delta_clip: float = 1e-4        # z = Phi^-1(delta) uses delta clipped to [clip, 1 - clip]
    grid_points: int = 201          # delta grid over (0, 1) for the positivity penalty


@dataclass(frozen=True)
class SplineConfig:
    """Bid-ask spline study (see docs/plans/bidask_spline_study.md). Vol quantities in vol points (x100)."""
    knot_step: float = 0.15         # target knot spacing in z
    max_basis: int = 60             # cap on B-spline coefficients per expiry
    tie_weight: float = 1e-2        # eps: pull toward mids, only to pick one curve among equals
    slack_cost: float = 2e3         # M: cost per vol point of breaking a bid/ask bound (exact L1)
    grid_points: int = 241          # evaluation grid across the quotes' z-range
    min_points: int = 6             # fewer bid/ask points than this: no fit
    max_abs_z: float = 4.0          # bid/ask points beyond |z| are left out (near-zero-delta noise)
    max_iv_spread: float = 0.15     # quotes wider than this (ask IV - bid IV) carry no information: dropped
    min_two_sided: int = 3          # fewer usable two-sided quotes than this: no fit


@dataclass(frozen=True)
class SplinePoints:
    """One expiry's constraint points: each quote's bid at (z_bid, iv_bid), ask at (z_ask, iv_ask); NaN = no bound."""
    strike: np.ndarray
    is_call: np.ndarray
    z_bid: np.ndarray
    iv_bid: np.ndarray
    z_ask: np.ndarray
    iv_ask: np.ndarray


@dataclass(frozen=True)
class WingPeak:
    z: float | None                 # where s'' peaks on this wing (None: no grid points on this side)
    s2: float | None                # peak curvature, vol units per z^2
    interior: bool                  # False when the peak sits at the outermost quote (still rising there)


@dataclass(frozen=True)
class SplineFit:
    status: str                     # ok | too_few | failed
    message: str | None
    points: SplinePoints
    grid_z: np.ndarray              # s, s1, s2 evaluated here (vol units, decimals)
    s: np.ndarray
    s1: np.ndarray
    s2: np.ndarray
    bid_active: np.ndarray          # bound touching the curve (multiplier > 0), per quote
    ask_active: np.ndarray
    bid_slack: np.ndarray           # how far the curve breaks the bound, vol units (0 = respected)
    ask_slack: np.ndarray
    roughness: float                # integral of s'''^2 over the grid, vol points^2
    monotone_ok: bool               # strike -> delta one-to-one along the curve (condition (*))
    s2_atm: float | None            # s''(0)
    put_peak: WingPeak              # z < 0
    call_peak: WingPeak             # z > 0
