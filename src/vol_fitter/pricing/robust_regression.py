"""L1 (least-absolute-deviation) regression helpers, via IRLS.

Plain OLS lets a single wide/stale wing quote dominate the fit; LAD is far
less sensitive to such outliers. Implemented as iteratively reweighted
least squares (IRLS): repeatedly solve a weighted-least-squares problem
with weights 1/|residual|, which converges to the L1 solution.

Both functions operate on one group (e.g. one expiry's strikes) at a time;
callers loop over groups.
"""
from __future__ import annotations

import numpy as np

from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)

_EPS = 1e-8


def lad_line_fit(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray | None = None,
    max_iter: int = 30,
    tol: float = 1e-8,
) -> tuple[float, float, float]:
    """Fit y = intercept + slope*x by LAD. Returns (intercept, slope, l1_loss)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 2:
        raise ValueError(f"need at least 2 points for a line fit, got {x.size}")
    w0 = np.ones_like(x) if weights is None else np.asarray(weights, dtype=float)

    intercept, slope = _weighted_line(x, y, w0)
    for _ in range(max_iter):
        resid = y - (intercept + slope * x)
        w = w0 / np.maximum(np.abs(resid), _EPS)
        new_intercept, new_slope = _weighted_line(x, y, w)
        if abs(new_intercept - intercept) < tol and abs(new_slope - slope) < tol:
            intercept, slope = new_intercept, new_slope
            break
        intercept, slope = new_intercept, new_slope

    l1_loss = float(np.sum(w0 * np.abs(y - (intercept + slope * x))))
    return intercept, slope, l1_loss


def lad_slope_through_origin(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray | None = None,
    max_iter: int = 30,
    tol: float = 1e-8,
) -> tuple[float, float]:
    """Fit y = slope*x (no intercept) by LAD. Returns (slope, l1_loss)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 1:
        raise ValueError("need at least 1 point for a slope-through-origin fit")
    w0 = np.ones_like(x) if weights is None else np.asarray(weights, dtype=float)

    slope = _weighted_slope(x, y, w0)
    for _ in range(max_iter):
        resid = y - slope * x
        w = w0 / np.maximum(np.abs(resid), _EPS)
        new_slope = _weighted_slope(x, y, w)
        if abs(new_slope - slope) < tol:
            slope = new_slope
            break
        slope = new_slope

    l1_loss = float(np.sum(w0 * np.abs(y - slope * x)))
    return slope, l1_loss


def _weighted_line(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    sw = np.sum(w)
    swx = np.sum(w * x)
    swxx = np.sum(w * x * x)
    swy = np.sum(w * y)
    swxy = np.sum(w * x * y)
    denom = sw * swxx - swx * swx
    if abs(denom) < _EPS:
        logger.warning("near-singular design in lad_line_fit; strikes may be too clustered")
        return float(swy / sw), 0.0
    slope = (sw * swxy - swx * swy) / denom
    intercept = (swy - slope * swx) / sw
    return float(intercept), float(slope)


def _weighted_slope(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    denom = np.sum(w * x * x)
    if denom < _EPS:
        logger.warning("near-zero design in lad_slope_through_origin; returning slope=0")
        return 0.0
    return float(np.sum(w * x * y) / denom)
