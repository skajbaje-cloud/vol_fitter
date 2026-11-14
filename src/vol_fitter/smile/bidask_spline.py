"""Bid-ask spline: the smoothest-curvature curve in z that passes between every bid and ask.

    minimise  integral s'''(z)^2 dz + eps * sum (s(z_mid) - mid)^2 + M * sum(bound violations)
    subject   s(z_bid,i) >= iv_bid,i,  s(z_ask,i) <= iv_ask,i   (softened by the M term)

s is a cubic B-spline on a uniform knot grid over the quotes' z-range. The s''' penalty is zero
for quadratics, so curvature only varies where the quotes force it to. Solved in vol points
(x100) for scale. See docs/plans/bidask_spline_study.md.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import BSpline

from vol_fitter.logging_setup import get_logger
from vol_fitter.smile.models import SplineConfig, SplineFit, SplinePoints, WingPeak
from vol_fitter.smile.qp_admm import SoftBoundQP

logger = get_logger(__name__)

_DEG = 3
_VP = 100.0               # vol points per unit vol
_ACTIVE_GAP = 1e-3        # vol points: a bound this close to the curve counts as touching
_MIN_SPREAD = 0.05        # vol points: floor on a quote's spread when weighting its mid


class BidAskSpline:
    def __init__(self, cfg: SplineConfig = SplineConfig(), solver: SoftBoundQP | None = None):
        self.cfg = cfg
        self.solver = solver or SoftBoundQP()

    def fit(self, pts: SplinePoints, T: float) -> SplineFit:
        has_b, has_a = np.isfinite(pts.iv_bid), np.isfinite(pts.iv_ask)
        n_bounds = int(has_b.sum() + has_a.sum())
        if n_bounds < self.cfg.min_points:
            return self._empty(pts, "too_few", f"only {n_bounds} usable bid/ask bounds (need {self.cfg.min_points})")
        n_two = int((has_b & has_a).sum())
        if n_two < self.cfg.min_two_sided:
            return self._empty(pts, "too_few", f"only {n_two} two-sided quotes tighter than "
                               f"{100 * self.cfg.max_iv_spread:.0f} vol points (need {self.cfg.min_two_sided})")

        zs = np.concatenate([pts.z_bid[has_b], pts.z_ask[has_a]])
        lo, hi = float(zs.min()), float(zs.max())
        knots = self._knots(lo, hi)
        n_coef = len(knots) - _DEG - 1
        basis = BSpline(knots, np.eye(n_coef), _DEG)

        # Constraint rows: bids are lower bounds, asks upper bounds (vol points).
        A = np.vstack([basis(pts.z_bid[has_b]), basis(pts.z_ask[has_a])])
        lower = np.concatenate([_VP * pts.iv_bid[has_b], np.full(int(has_a.sum()), -np.inf)])
        upper = np.concatenate([np.full(int(has_b.sum()), np.inf), _VP * pts.iv_ask[has_a]])

        P = self._roughness_matrix(basis, knots)
        Bm, mid = self._tie_points(basis, pts, has_b, has_a)
        H = 2.0 * (P + self.cfg.tie_weight * Bm.T @ Bm)
        q = -2.0 * self.cfg.tie_weight * Bm.T @ mid
        scale = float(np.mean(np.diag(H)))        # objective to O(1) for ADMM; M scales with it
        c, y, polished = self.solver.solve(H / scale, q / scale, A, lower, upper, self.cfg.slack_cost / scale)
        if not np.all(np.isfinite(c)):
            return self._empty(pts, "failed", "QP solver returned non-finite coefficients")

        fit_b, fit_a = basis(pts.z_bid[has_b]) @ c, basis(pts.z_ask[has_a]) @ c
        bid_slack, ask_slack = np.zeros(len(has_b)), np.zeros(len(has_a))
        bid_slack[has_b] = np.maximum(lower[: has_b.sum()] - fit_b - _ACTIVE_GAP, 0.0) / _VP
        ask_slack[has_a] = np.maximum(fit_a - upper[has_b.sum():] - _ACTIVE_GAP, 0.0) / _VP
        bid_active, ask_active = np.zeros(len(has_b), bool), np.zeros(len(has_a), bool)
        bid_active[has_b] = np.abs(fit_b - lower[: has_b.sum()]) <= _ACTIVE_GAP
        ask_active[has_a] = np.abs(fit_a - upper[has_b.sum():]) <= _ACTIVE_GAP

        grid = np.linspace(lo, hi, self.cfg.grid_points)
        s, s1, s2 = (basis.derivative(nu)(grid) @ c / _VP if nu else basis(grid) @ c / _VP for nu in range(3))
        monotone = bool(np.all(s + s1 * (grid + s * np.sqrt(T)) > 0))
        s2_atm = float((basis.derivative(2)(np.array([0.0])) @ c)[0] / _VP) if lo < 0 < hi else None
        if not polished:
            logger.info("bid-ask spline: polish not accepted; using the ADMM solution")
        return SplineFit(
            status="ok", message=None if monotone else "strike -> delta is not one-to-one somewhere on the curve",
            points=pts, grid_z=grid, s=s, s1=s1, s2=s2,
            bid_active=bid_active, ask_active=ask_active, bid_slack=bid_slack, ask_slack=ask_slack,
            roughness=float(c @ P @ c), monotone_ok=monotone, s2_atm=s2_atm,
            put_peak=self._peak(grid, s2, grid < 0, edge_first=True),
            call_peak=self._peak(grid, s2, grid > 0, edge_first=False),
        )

    def _knots(self, lo: float, hi: float) -> np.ndarray:
        n_int = int(np.clip(np.ceil((hi - lo) / self.cfg.knot_step), 1, self.cfg.max_basis - _DEG))
        inner = np.linspace(lo, hi, n_int + 1)
        return np.concatenate([[lo] * _DEG, inner, [hi] * _DEG])

    @staticmethod
    def _roughness_matrix(basis: BSpline, knots: np.ndarray) -> np.ndarray:
        """integral of s'''^2 = c'Pc; s''' is constant on each knot interval of a cubic spline."""
        u = np.unique(knots)
        mids, widths = 0.5 * (u[1:] + u[:-1]), np.diff(u)
        D3 = basis.derivative(3)(mids)
        return D3.T @ (widths[:, None] * D3)

    @staticmethod
    def _tie_points(basis: BSpline, pts: SplinePoints, has_b, has_a):
        """Mid of each two-sided quote, on its bid-ask segment, weighted by 1/spread^2 (rows scaled by
        sqrt(weight)) so tight quotes pick the curve and wide ones (deep ITM, illiquid) barely pull.
        One-sided quotes don't pull."""
        both = has_b & has_a
        if both.sum() < 3:          # too few mids to pin a quadratic: pull toward every bound instead
            z = np.concatenate([pts.z_bid[has_b], pts.z_ask[has_a]])
            return basis(z), _VP * np.concatenate([pts.iv_bid[has_b], pts.iv_ask[has_a]])
        z = 0.5 * (pts.z_bid[both] + pts.z_ask[both])
        spread = np.maximum(_VP * np.abs(pts.iv_ask[both] - pts.iv_bid[both]), _MIN_SPREAD)
        w = 1.0 / spread ** 2
        r = np.sqrt(w / w.mean())[:, None]
        return r * basis(z), r[:, 0] * _VP * 0.5 * (pts.iv_bid[both] + pts.iv_ask[both])

    @staticmethod
    def _peak(grid, s2, side, edge_first: bool) -> WingPeak:
        if not side.any():
            return WingPeak(z=None, s2=None, interior=False)
        g, v = grid[side], s2[side]
        i = int(np.argmax(v))
        edge = 0 if edge_first else len(g) - 1      # the outermost quote on this wing
        return WingPeak(z=float(g[i]), s2=float(v[i]), interior=i != edge)

    def _empty(self, pts: SplinePoints, status: str, message: str) -> SplineFit:
        n, e = len(pts.strike), np.array([])
        return SplineFit(status=status, message=message, points=pts, grid_z=e, s=e, s1=e, s2=e,
                         bid_active=np.zeros(n, bool), ask_active=np.zeros(n, bool),
                         bid_slack=np.zeros(n), ask_slack=np.zeros(n), roughness=float("nan"),
                         monotone_ok=True, s2_atm=None,
                         put_peak=WingPeak(None, None, False), call_peak=WingPeak(None, None, False))
