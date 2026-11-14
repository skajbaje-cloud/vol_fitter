"""Bid-ask spline study on synthetic smiles with a known answer (pure maths, no DB or LSEG)."""
import numpy as np
import pandas as pd

from vol_fitter.smile.bidask_spline import BidAskSpline
from vol_fitter.smile.models import SplinePoints
from vol_fitter.smile.qp_admm import SoftBoundQP
from vol_fitter.smile.spline_points import SplinePointBuilder, z_of

T, F = 0.25, 100.0


def _quotes(true_vol, half_spread=0.005, z=np.linspace(-2.5, 2.5, 41)):
    """Quotes whose true IV is true_vol(z) at their own z; bid/ask = true -/+ half_spread."""
    sig = true_vol(z)
    k = sig * np.sqrt(T) * (z + 0.5 * sig * np.sqrt(T))     # inverts z(sigma; k)
    return pd.DataFrame({"strike": F * np.exp(k), "is_call": z > 0,
                         "bid_iv": sig - half_spread, "ask_iv": sig + half_spread})


def _fit(true_vol, **kw):
    pts = SplinePointBuilder().build(_quotes(true_vol, **kw), F, T)
    return BidAskSpline().fit(pts, T)


def test_z_axis_increases_with_strike():
    assert z_of(0.2, np.log(120 / F), T) > 0 > z_of(0.2, np.log(80 / F), T)


def test_bid_and_ask_sit_at_different_z():
    pts = SplinePointBuilder().build(_quotes(lambda z: 0.2 + 0 * z, half_spread=0.01), F, T)
    far = np.argmax(np.abs(pts.z_bid))
    assert abs(pts.z_bid[far] - pts.z_ask[far]) > 0.05      # ~0.1 per vol point out at |z| ~ 2.5


def test_quadratic_smile_recovered_with_flat_curvature():
    f = _fit(lambda z: 0.20 - 0.03 * z + 0.01 * z ** 2)
    assert f.status == "ok" and f.monotone_ok
    assert (f.bid_slack == 0).all() and (f.ask_slack == 0).all()
    assert np.allclose(f.s2, 0.02, atol=0.002)               # s'' = 2 * 0.01 everywhere


def test_curvature_peaks_found_in_both_wings():
    def vol(z):   # one hyperbola per wing: curvature bumps at z = -1.5 and +1.2
        return 0.2 - 0.02 * z + 0.03 * (np.sqrt((z + 1.5) ** 2 + 0.25) - 0.5) + 0.02 * (np.sqrt((z - 1.2) ** 2 + 0.25) - 0.5)
    f = _fit(vol, half_spread=0.0005, z=np.linspace(-3, 3, 81))
    assert f.put_peak.interior and abs(f.put_peak.z + 1.5) < 0.3
    assert f.call_peak.interior and abs(f.call_peak.z - 1.2) < 0.3
    assert f.put_peak.s2 > f.s2_atm and f.call_peak.s2 > f.s2_atm


def test_one_bad_quote_is_broken_alone():
    q = _quotes(lambda z: 0.20 - 0.03 * z + 0.01 * z ** 2)
    q.loc[20, ["bid_iv", "ask_iv"]] = [0.30, 0.31]             # 10 vol points off, mid-smile
    f = BidAskSpline().fit(SplinePointBuilder().build(q, F, T), T)
    broken = np.flatnonzero((f.bid_slack > 0) | (f.ask_slack > 0))
    assert broken.tolist() == [20]


def test_one_sided_quotes_and_too_few():
    q = _quotes(lambda z: 0.2 + 0 * z).head(3)                 # 5 bounds, below min_points (6)
    q.loc[0, "bid_iv"] = 0.0                                   # zero bid: no lower bound
    pts = SplinePointBuilder().build(q, F, T)
    assert np.isnan(pts.iv_bid[0]) and np.isfinite(pts.iv_ask[0])
    assert BidAskSpline().fit(pts, T).status == "too_few"


def test_soft_bound_qp_holds_or_breaks_by_price():
    H, q, A = np.array([[2.0]]), np.array([-6.0]), np.array([[1.0]])   # min (x-3)^2, wants x = 3
    x, y, ok = SoftBoundQP().solve(H, q, A, np.array([-np.inf]), np.array([1.0]), M=100.0)
    assert ok and abs(x[0] - 1.0) < 1e-9 and y[0] > 0                   # bound x <= 1 held
    x, y, ok = SoftBoundQP().solve(H, q, A, np.array([-np.inf]), np.array([1.0]), M=1.0)
    assert ok and abs(x[0] - 2.5) < 1e-6 and abs(y[0] - 1.0) < 1e-9     # cheaper to break by 1.5
