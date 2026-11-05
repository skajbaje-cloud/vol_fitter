"""Plain data holders for the pricing library.

Bulk operations (pricing/IV for a whole snapshot) work on DataFrames of
these fields directly for efficiency; the dataclasses here are for the
one-row-per-expiry forward result and for single-quote convenience/tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ForwardResult:
    expiry_date: date
    T: float
    forward: float
    discount_factor: float
    n_strikes_forward: int
    n_strikes_df: int
    forward_fit_resid: float
    df_fit_resid: float


@dataclass(frozen=True)
class PricedQuote:
    instrument: str
    strike: float
    expiry_date: date
    T: float
    is_call: bool
    bid: float
    ask: float
    bid_iv: float
    ask_iv: float
    bid_delta: float
    ask_delta: float
    bid_gamma: float
    ask_gamma: float
    bid_vega: float
    ask_vega: float
    bid_theta: float
    ask_theta: float
    bid_rho: float
    ask_rho: float
