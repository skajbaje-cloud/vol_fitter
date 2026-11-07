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
