import numpy as np
import pytest

from vol_fitter.pricing.robust_regression import lad_line_fit, lad_slope_through_origin


def test_lad_line_fit_recovers_clean_line():
    x = np.linspace(-10, 10, 21)
    y = 3.0 + 2.0 * x
    intercept, slope, loss = lad_line_fit(x, y)
    assert intercept == pytest.approx(3.0, abs=1e-6)
    assert slope == pytest.approx(2.0, abs=1e-6)
    assert loss == pytest.approx(0.0, abs=1e-6)


def test_lad_line_fit_resists_one_big_outlier():
    x = np.linspace(-10, 10, 21)
    y = 3.0 + 2.0 * x
    y_outlier = y.copy()
    y_outlier[10] += 500.0  # one wild point

    intercept_ols = np.polyfit(x, y_outlier, 1)[::-1]
    intercept_lad, slope_lad, _ = lad_line_fit(x, y_outlier)

    assert slope_lad == pytest.approx(2.0, abs=0.05)
    assert intercept_lad == pytest.approx(3.0, abs=0.5)
    # OLS should be visibly dragged off by the outlier; LAD should not.
    assert abs(intercept_ols[0] - 3.0) > abs(intercept_lad - 3.0)


def test_lad_slope_through_origin_recovers_clean_slope():
    x = np.linspace(1, 20, 20)
    y = 0.95 * x
    slope, loss = lad_slope_through_origin(x, y)
    assert slope == pytest.approx(0.95, abs=1e-6)
    assert loss == pytest.approx(0.0, abs=1e-6)


def test_lad_slope_through_origin_resists_outlier():
    x = np.linspace(1, 20, 20)
    y = 0.95 * x
    y_outlier = y.copy()
    y_outlier[0] += 200.0

    slope, _ = lad_slope_through_origin(x, y_outlier)
    assert slope == pytest.approx(0.95, abs=0.1)


def test_line_fit_requires_two_points():
    with pytest.raises(ValueError):
        lad_line_fit(np.array([1.0]), np.array([1.0]))
