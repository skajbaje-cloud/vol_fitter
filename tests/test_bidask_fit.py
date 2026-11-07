"""bidask_fit tests: the 7 spec cases plus bid-only quotes and previous-fit anchoring."""
from __future__ import annotations

import logging

import numpy as np
import pytest

from bidask_toys import TRUE_P, LinearSmile, QuadraticSmile, make_quotes
from vol_fitter.bidask_fit import FitConfig, FitStatus, fit
from vol_fitter.bidask_fit.models import SpreadFrame
from vol_fitter.bidask_fit.penalty import ExpWallPenalty
from vol_fitter.bidask_fit.spread import SpreadBuilder

LB, UB = np.array([0.01, -2, 0.01, -2]), np.array([2.0, 2, 2, 2])
P0 = np.array([0.25, 0.0, 0.25, 0.0])
MODEL = LinearSmile()


def _shift(q, i, n_half_spreads):
    h = 0.5 * (q.loc[i, "ask_iv"] - q.loc[i, "bid_iv"])
    q.loc[i, ["bid_iv", "ask_iv"]] -= n_half_spreads * h


# 1 -------------------------------------------------------------------------
def test_recovers_params_all_inside():
    r = fit(MODEL, make_quotes(), P0, (LB, UB))
    assert r.status == FitStatus.OK
    assert r.pct_inside == 1.0
    np.testing.assert_allclose(r.p, TRUE_P, atol=0.01)
    assert r.p_first is None and not r.flags


# 2 -------------------------------------------------------------------------
def test_wall_continuous_with_zero_slope_at_edge():
    cfg = FitConfig()
    pen = ExpWallPenalty(cfg)
    bid, ask = 0.19, 0.21
    q = make_quotes().iloc[:1].assign(bid_iv=bid, ask_iv=ask)
    spread = SpreadBuilder(cfg).build(q)
    f = lambda s: pen.wall(pen.raw_x(np.array([s]), spread))[0]
    h = 0.5 * (ask - bid)
    for edge in (ask, bid):
        assert f(edge) == pytest.approx(0.0, abs=1e-20)
        for d in (1e-4, 1e-5, 1e-6):
            slope = (f(edge + d) - f(edge - d)) / (2 * d)
            # near the edge wall ~ (c x)^2 / 2, so the central difference is c^2 d / (4 h^2) -> 0
            assert abs(slope) == pytest.approx(cfg.c_w ** 2 * d / (4 * h ** 2), rel=1e-2)
    s, d = ask + 1.0 * h, 1e-7                   # one half-spread outside: analytic slope c(e^{cx}-1)/h
    num = (f(s + d) - f(s - d)) / (2 * d)
    assert num == pytest.approx(cfg.c_w * np.expm1(cfg.c_w * 1.0) / h, rel=1e-4)


# 3 -------------------------------------------------------------------------
def test_one_sided_quotes_bind_only_on_ask():
    cfg = FitConfig()
    pen = ExpWallPenalty(cfg)
    q = make_quotes().iloc[:1].assign(bid_iv=np.nan, ask_iv=0.20)
    spread = SpreadBuilder(cfg).build(q)
    v_ask, v_bid = pen.violations(np.array([0.05]), spread)          # far below the ask: free
    assert v_ask[0] == 0 and v_bid[0] == 0
    v_ask, _ = pen.violations(np.array([0.21]), spread)              # above the ask: x in h_min units
    assert v_ask[0] == pytest.approx(0.01 / cfg.h_min)

    q = make_quotes()
    ask_only = q.index[::2]
    q.loc[ask_only, "bid_iv"] = np.nan
    r = fit(MODEL, q, P0, (LB, UB))
    t = r.quotes
    assert (t.loc[ask_only, "v_bid"] == 0).all()
    assert t.loc[ask_only, "v_ask"].max() < 0.01           # at most a hair over the soft edge
    assert t.drop(index=ask_only)["inside"].all()
    np.testing.assert_allclose(r.p, TRUE_P, atol=0.015)


def test_bid_only_quotes_bind_only_on_bid():
    cfg = FitConfig()
    pen = ExpWallPenalty(cfg)
    q = make_quotes().iloc[:1].assign(bid_iv=0.20, ask_iv=np.nan)
    spread = SpreadBuilder(cfg).build(q)
    v_ask, v_bid = pen.violations(np.array([0.90]), spread)
    assert v_ask[0] == 0 and v_bid[0] == 0
    _, v_bid = pen.violations(np.array([0.19]), spread)
    assert v_bid[0] == pytest.approx(0.01 / cfg.h_min)


# 4 -------------------------------------------------------------------------
def test_stale_quote_is_outlier_and_refit_restores_neighbours():
    q = make_quotes()
    _shift(q, 12, 4.5)                         # within the wall's reach (x < x_max): it drags the fit
    r = fit(MODEL, q, P0, (LB, UB))
    t = r.quotes
    assert t.loc[12, "classification"] == "outlier"
    assert t.loc[12, "excluded"]
    assert r.p_first is not None and r.refit_delta is not None
    assert r.pct_inside_by_expiry["E1"] == 1.0  # neighbours back inside after the refit
    np.testing.assert_allclose(r.p, TRUE_P, atol=0.01)


def test_quote_beyond_x_max_is_inert_and_reported():
    q = make_quotes()
    _shift(q, 12, 12)                          # 6 full spreads: past x_max, so no gradient at all
    r = fit(MODEL, q, P0, (LB, UB))
    t = r.quotes
    assert t.loc[12, "x_capped"] and t.loc[12, "classification"] == "isolated"
    assert r.p_first is None
    assert t.drop(index=12)["inside"].all()


# 5 -------------------------------------------------------------------------
def test_unreachable_wing_is_model_miss_and_kept():
    def wing(qq):
        return LinearSmile()(TRUE_P, qq) + 0.08 * (qq["k"].to_numpy() <= -0.3)
    r = fit(MODEL, make_quotes(wing), P0, (LB, UB))
    t = r.quotes
    assert (t["classification"] == "model_miss").sum() >= 4
    assert (t["classification"] != "outlier").all()
    assert not t["excluded"].any() and r.p_first is None


# 6 -------------------------------------------------------------------------
def test_ten_pct_corrupted_trips_guard(caplog):
    rng = np.random.default_rng(3)
    q = make_quotes()
    for i, s in zip(rng.choice(len(q), len(q) // 10, replace=False), rng.choice([-1, 1], len(q) // 10)):
        _shift(q, i, 5 * s)
    with caplog.at_level(logging.WARNING):
        r = fit(MODEL, q, P0, (LB, UB))
    assert any(f.startswith("guard_") for f in r.flags)
    assert any("guard_" in rec.message for rec in caplog.records)
    assert not r.quotes["excluded"].any() and r.p_first is None


# 7 -------------------------------------------------------------------------
def test_swapping_model_needs_no_module_change():
    true_q = np.array([0.20, -0.30, 0.8, 0.22, -0.15, 0.4])
    q = make_quotes(lambda qq: QuadraticSmile()(true_q, qq))
    lb, ub = np.tile([0.01, -2, -5], 2), np.tile([2.0, 2, 5], 2)
    r = fit(QuadraticSmile(), q, np.tile([0.25, 0, 0], 2), (lb, ub))
    assert r.pct_inside == 1.0
    np.testing.assert_allclose(r.p, true_q, atol=0.05)
    assert fit(MODEL, q, P0, (LB, UB)).pct_inside < 1.0   # the linear model can't do it


# anchoring ---------------------------------------------------------------------
def test_anchor_pulls_toward_previous_fit_while_staying_inside():
    q = make_quotes()
    p_prev = TRUE_P + np.array([0.001, 0.004, -0.001, 0.004])  # yesterday's fit, still inside today's spreads
    free = fit(MODEL, q, P0, (LB, UB))
    anch = fit(MODEL, q, P0, (LB, UB), cfg=FitConfig(lam_a=1e4), p_prev=p_prev)
    assert anch.pct_inside == 1.0 and not anch.anchor_relaxed and anch.anchor_lambda == 1e4
    assert np.linalg.norm(anch.p - p_prev) < 0.05 * np.linalg.norm(free.p - p_prev)


def test_anchor_guard_backs_off_lambda_instead_of_leaving_quotes_outside():
    q = make_quotes()
    p_prev = TRUE_P + np.array([0.002, 0.01, -0.002, 0.01])    # partly conflicts with today's walls
    r = fit(MODEL, q, P0, (LB, UB), cfg=FitConfig(lam_a=1e4), p_prev=p_prev)
    assert r.pct_inside == 1.0
    assert 0 < r.anchor_lambda < 1e4 and not r.anchor_relaxed


def test_anchor_guard_relaxes_when_previous_fit_is_off_market():
    q = make_quotes()
    p_prev = TRUE_P + np.array([0.05, 0.0, 0.05, 0.0])        # 5 vol points away: can't stay inside
    r = fit(MODEL, q, P0, (LB, UB), cfg=FitConfig(lam_a=1e8), p_prev=p_prev)
    assert r.anchor_relaxed and "anchor_relaxed" in r.flags
    assert r.pct_inside == 1.0


def test_dropped_quotes_reported():
    q = make_quotes()
    q.loc[[3, 40], ["bid_iv", "ask_iv"]] = np.nan
    r = fit(MODEL, q, P0, (LB, UB))
    assert (r.quotes["classification"] == "dropped").sum() == 2
    assert r.n_quotes == len(q) - 2 and r.pct_inside == 1.0
