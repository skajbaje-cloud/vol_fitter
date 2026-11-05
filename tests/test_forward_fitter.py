from datetime import date

import numpy as np
import pandas as pd
import pytest

from vol_fitter.pricing.forward_fitter import ForwardFitter


def _synthetic_quotes(F: float, DF: float, T: float, strikes: np.ndarray, outlier_idx: int | None = None) -> pd.DataFrame:
    """Build call/put quotes whose mid-price difference exactly satisfies
    put-call parity (mid_c - mid_p = DF*(F-K)), optionally with one strike's
    put quote badly distorted to simulate a stale/bad market.
    """
    expiry = date(2027, 1, 15)
    mid_c = np.full_like(strikes, 10.0)
    mid_p = mid_c - DF * (F - strikes)
    if outlier_idx is not None:
        mid_p[outlier_idx] += 50.0

    calls = pd.DataFrame({
        "strike": strikes, "is_call": True, "bid": mid_c, "ask": mid_c,
        "expiry_date": expiry, "T": T,
    })
    puts = pd.DataFrame({
        "strike": strikes, "is_call": False, "bid": mid_p, "ask": mid_p,
        "expiry_date": expiry, "T": T,
    })
    return pd.concat([calls, puts], ignore_index=True)


def test_recovers_known_forward_and_df_with_no_outliers():
    strikes = np.linspace(80, 120, 21)
    quotes = _synthetic_quotes(F=100.0, DF=0.98, T=0.5, strikes=strikes)

    results = ForwardFitter().fit_all(quotes)
    assert len(results) == 1
    result = results[0]
    assert result.forward == pytest.approx(100.0, abs=1e-4)
    assert result.discount_factor == pytest.approx(0.98, abs=1e-4)


def test_df_stage_resists_a_wing_outlier():
    strikes = np.linspace(80, 120, 21)
    # Outlier at the far wing (K=120), well outside the narrow F-band.
    outlier_idx = int(np.argmax(strikes))
    quotes = _synthetic_quotes(F=100.0, DF=0.98, T=0.5, strikes=strikes, outlier_idx=outlier_idx)

    results = ForwardFitter().fit_all(quotes)
    result = results[0]
    assert result.forward == pytest.approx(100.0, abs=1e-3)
    assert result.discount_factor == pytest.approx(0.98, abs=0.01)


def test_skips_expiry_with_too_few_common_strikes():
    expiry = date(2027, 1, 15)
    quotes = pd.DataFrame({
        "strike": [100.0], "is_call": [True], "bid": [10.0], "ask": [10.0],
        "expiry_date": [expiry], "T": [0.5],
    })
    results = ForwardFitter().fit_all(quotes)
    assert results == []
