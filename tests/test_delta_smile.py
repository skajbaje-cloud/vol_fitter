"""Phi^-1(delta) quadratic-wing smile model, its fit frame, and a round trip through bidask_fit."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from vol_fitter.bidask_fit import fit
from vol_fitter.smile import DeltaSmileModel, FitFrameBuilder, SmileParams

MODEL = DeltaSmileModel()


def test_atm_and_skew_are_value_and_slope_at_50_delta():
    p = [0.18, 0.03, 0.04, 0.006]
    assert MODEL.vol_at_delta(p, [0.5])[0] == pytest.approx(0.18)
    d = 1e-6
    slope = (MODEL.vol_at_z(p, [d])[0] - MODEL.vol_at_z(p, [-d])[0]) / (2 * d)
    assert slope == pytest.approx(0.03, abs=1e-6)


def test_kappa_is_vol_added_at_z_plus_minus_one():
    put_only, call_only = [0.0, 0.0, 0.05, 0.0], [0.0, 0.0, 0.0, 0.02]
    assert MODEL.vol_at_z(put_only, [1.0, -1.0, 0.0]).tolist() == pytest.approx([0.05, 0.0, 0.0])
    assert MODEL.vol_at_z(call_only, [1.0, -1.0, 0.0]).tolist() == pytest.approx([0.0, 0.02, 0.0])
    # z = +1 is call delta Phi(1) ~ 0.841, i.e. about the 16-delta put
    assert MODEL.vol_at_delta(put_only, [norm.cdf(1.0)])[0] == pytest.approx(0.05)


def test_put_wing_keeps_rising_and_convexity_is_two_kappa():
    p = [0.18, 0.03, 0.04, 0.006]
    v = MODEL.vol_at_delta(p, np.linspace(0.85, 0.999, 60))
    assert np.all(np.diff(v) > 0)
    z, d = np.array([1.5, -1.5]), 1e-4
    conv = (MODEL.vol_at_z(p, z + d) - 2 * MODEL.vol_at_z(p, z) + MODEL.vol_at_z(p, z - d)) / d ** 2
    assert conv == pytest.approx([2 * 0.04, 2 * 0.006], rel=1e-4)


def test_params_roundtrip():
    p = SmileParams(0.2, 0.03, 0.04, 0.006)
    assert SmileParams.from_vector(p.to_vector()) == p


def test_positivity_penalty():
    assert not MODEL.positivity_penalty([0.2, 0.03, 0.04, 0.006]).any()
    assert MODEL.positivity_penalty([0.05, 0.1, 0.0, 0.0]).max() > 0     # negative deep on the call side


def test_fit_frame_forward_call_delta_from_bid_ask_deltas():
    DF = 0.98
    quotes = pd.DataFrame({
        "instrument": ["C1", "P1", "P2"],
        "expiry_date": [date(2027, 1, 15)] * 3,
        "T": [0.5] * 3, "strike": [100.0, 90.0, 80.0], "is_call": [True, False, False],
        "bid_iv": [0.20, 0.25, np.nan], "ask_iv": [0.22, 0.27, 0.35],
        "bid_delta": [DF * 0.40, -DF * 0.20, np.nan],
        "ask_delta": [DF * 0.44, -DF * 0.22, -DF * 0.10],
    })
    mats = pd.DataFrame({"expiry_date": [date(2027, 1, 15)], "discount_factor": [DF]})
    f = FitFrameBuilder().build(quotes, mats)
    np.testing.assert_allclose(f["delta"], [0.42, 0.79, 0.90])     # call: mean; puts: 1 + delta/DF
    np.testing.assert_allclose(f["z"], norm.ppf([0.42, 0.79, 0.90]))
    np.testing.assert_allclose(f["otm_delta"], [0.42, 0.21, 0.10])
    assert list(f["expiry"].unique()) == [date(2027, 1, 15)]


def test_recovers_synthetic_smile_through_bidask_fit():
    rng = np.random.default_rng(1)
    true_p = np.array([0.18, 0.03, 0.04, 0.006])
    delta = np.linspace(0.01, 0.99, 40)
    sig = MODEL.vol_at_delta(true_p, delta)
    h = rng.uniform(0.002, 0.006, len(delta))
    mid = sig + rng.uniform(-0.4, 0.4, len(delta)) * h
    q = pd.DataFrame({"expiry": "E", "delta": delta, "bid_iv": mid - h, "ask_iv": mid + h})
    q.loc[q.index[:5], "bid_iv"] = np.nan                       # deep OTM call quotes with no bid

    r = fit(MODEL, q, MODEL.initial_guess(q), MODEL.bounds(), model_penalty=MODEL.positivity_penalty)
    assert r.status.value == "ok" and r.pct_inside >= 0.97
    np.testing.assert_allclose(r.p, true_p, atol=0.005)


def test_initial_guess_is_reasonable():
    delta = np.linspace(0.1, 0.9, 30)
    sig = 0.2 + 0.03 * norm.ppf(delta)
    q = pd.DataFrame({"delta": delta, "bid_iv": sig - 0.005, "ask_iv": sig + 0.005})
    p0 = MODEL.initial_guess(q)
    assert p0[0] == pytest.approx(0.2, abs=0.005) and p0[1] == pytest.approx(0.03, abs=0.005)
