"""Request/response shapes for the bid-ask spline (curvature) study. Vols are decimals; s2 is vol per z^2."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class SplinePointsOut(BaseModel):
    """Per quote: bid bound at (z_bid, iv_bid), ask bound at (z_ask, iv_ask); null where there is no bound."""
    strike: list[float]
    is_call: list[bool]
    z_bid: list[float | None]
    iv_bid: list[float | None]
    z_ask: list[float | None]
    iv_ask: list[float | None]
    bid_active: list[bool]
    ask_active: list[bool]
    bid_slack: list[float]
    ask_slack: list[float]


class WingPeakOut(BaseModel):
    z: float | None
    s2: float | None
    interior: bool


class SmileModelOut(BaseModel):
    sigma_atm: float
    skew: float
    kappa_put: float
    kappa_call: float


class SplineExpiryOut(BaseModel):
    expiry: date
    T: float
    forward: float
    status: str                      # ok | too_few | failed
    message: str | None
    n_bounds: int
    n_active: int
    n_broken: int
    max_break: float                 # largest bound violation, vol units
    roughness: float | None
    monotone_ok: bool
    s2_atm: float | None
    put_peak: WingPeakOut
    call_peak: WingPeakOut
    model: SmileModelOut | None      # stored per-expiry fit, on the old z = Phi^-1(call delta) axis
    grid_z: list[float]
    s: list[float]
    s1: list[float]
    s2: list[float]
    points: SplinePointsOut
