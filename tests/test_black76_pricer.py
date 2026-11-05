import numpy as np
import pytest

from vol_fitter.pricing import black76_formulas
from vol_fitter.pricing.black76_pricer import Black76Pricer

pricer = Black76Pricer()


def _grid():
    F = np.array([100.0] * 10)
    K = np.array([60, 80, 95, 100, 105, 120, 150, 90, 110, 100], dtype=float)
    T = np.array([1.0, 0.25, 0.5, 1.0, 2.0, 0.5, 0.75, 0.05, 3.0, 1.5])
    sigma = np.array([0.15, 0.20, 0.25, 0.30, 0.18, 0.40, 0.22, 0.35, 0.12, 0.28])
    DF = np.array([0.99, 0.98, 0.97, 0.95, 0.90, 0.97, 0.96, 0.995, 0.85, 0.92])
    is_call = np.array([True, True, True, True, True, False, False, False, False, False])
    return F, K, T, sigma, DF, is_call


def test_price_implied_vol_round_trip():
    F, K, T, sigma, DF, is_call = _grid()
    price = pricer.price(F, K, T, sigma, DF, is_call)
    recovered = pricer.implied_vol(price, F, K, T, DF, is_call)
    np.testing.assert_allclose(recovered, sigma, atol=1e-6)


def test_implied_vol_handles_mixed_calls_and_puts_both_sides_of_money():
    # K < F (call ITM / put OTM) and K > F (call OTM / put ITM), both option types.
    F = np.full(4, 100.0)
    K = np.array([80.0, 80.0, 120.0, 120.0])
    is_call = np.array([True, False, True, False])
    T = np.full(4, 1.0)
    sigma_true = np.full(4, 0.22)
    DF = np.full(4, 0.96)

    price = black76_formulas.price(F, K, T, sigma_true, DF, is_call)
    recovered = pricer.implied_vol(price, F, K, T, DF, is_call)
    np.testing.assert_allclose(recovered, sigma_true, atol=1e-6)


def test_implied_vol_nan_for_arbitrage_violating_price():
    F, K, T, sigma, DF, is_call = _grid()
    price = pricer.price(F, K, T, sigma, DF, is_call)
    price[0] = -5.0  # negative price is never valid
    recovered = pricer.implied_vol(price, F, K, T, DF, is_call)
    assert np.isnan(recovered[0])
    assert not np.any(np.isnan(recovered[1:]))


@pytest.mark.parametrize("bump_var", ["F", "sigma", "T", "DF"])
def test_greeks_match_finite_differences(bump_var):
    F, K, T, sigma, DF, is_call = _grid()
    h = 1e-4
    greeks = pricer.greeks(F, K, T, sigma, DF, is_call)

    if bump_var == "F":
        up = pricer.price(F * (1 + h), K, T, sigma, DF, is_call)
        down = pricer.price(F * (1 - h), K, T, sigma, DF, is_call)
        fd = (up - down) / (2 * h * F)
        np.testing.assert_allclose(fd, greeks["delta"], atol=1e-4, rtol=1e-4)
    elif bump_var == "sigma":
        up = pricer.price(F, K, T, sigma + h, DF, is_call)
        down = pricer.price(F, K, T, sigma - h, DF, is_call)
        fd = (up - down) / (2 * h)
        np.testing.assert_allclose(fd, greeks["vega"], atol=1e-4, rtol=1e-4)
    elif bump_var == "T":
        # Theta holds the discount RATE fixed, not DF (DF necessarily moves
        # with T once r is fixed) -- so re-derive DF at T+-h from r=-ln(DF)/T.
        r = -np.log(DF) / T
        up = pricer.price(F, K, T + h, sigma, np.exp(-r * (T + h)), is_call)
        down = pricer.price(F, K, T - h, sigma, np.exp(-r * (T - h)), is_call)
        fd = -(up - down) / (2 * h)  # theta = -dV/dT
        np.testing.assert_allclose(fd, greeks["theta"], atol=1e-3, rtol=1e-3)
    elif bump_var == "DF":
        # r = -ln(DF)/T; bump r by h <=> DF -> DF * exp(-h*T)
        DF_up = DF * np.exp(-h * T)
        DF_down = DF * np.exp(h * T)
        up = pricer.price(F, K, T, sigma, DF_up, is_call)
        down = pricer.price(F, K, T, sigma, DF_down, is_call)
        fd = (up - down) / (2 * h)
        np.testing.assert_allclose(fd, greeks["rho"], atol=1e-3, rtol=1e-3)


def test_gamma_is_derivative_of_delta_wrt_forward():
    F, K, T, sigma, DF, is_call = _grid()
    h = 1e-4
    up = pricer.greeks(F * (1 + h), K, T, sigma, DF, is_call)["delta"]
    down = pricer.greeks(F * (1 - h), K, T, sigma, DF, is_call)["delta"]
    fd_gamma = (up - down) / (2 * h * F)
    gamma = pricer.greeks(F, K, T, sigma, DF, is_call)["gamma"]
    np.testing.assert_allclose(fd_gamma, gamma, atol=1e-4, rtol=1e-3)
