"""Chain picking, chain summaries and the monthly-expiry filter (pure logic, no LSEG)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from vol_fitter.snapshot.chain_check import summarise
from vol_fitter.snapshot.expiry_filter import filter_expiries, monthly_expiries, third_friday
from vol_fitter.snapshot.name_lookup import pick_chains, ric_root

# Real search hits for .SPX (trimmed titles), plus futures/ATM/per-expiry noise.
SPX_ROWS = [
    ("0#ES:FV", "CME E-Mini S&P 500 Index Future Chain Contract"),
    ("0#SPXO*.U", "OPRA Cboe S&P 500 AM Settled Expiring Weekly Index Option Chain Contracts"),
    ("0#SPXW*.U", "OPRA S&P 500 Index Option Chain Contracts"),
    ("0#SPX*.U", "OPRA S&P 500 Index Option Chain Contracts"),
    ("Z#SPX*.U", "OPRA S&P 500 Index Option Chain Contracts"),
]
STOXX_ROWS = [
    ("0#STXE*.EX++", "Eurex EURO STOXX 50 Index Option ATM Chain Contracts"),
    ("0#STXEZ26*.EX", "Eurex EURO STOXX 50 Index Option Dec 2026 Monthly Option Chain"),
    ("0#STXE5W*.EX", "Eurex EURO STOXX 50 5th Friday Weekly Index Option Chain Contract"),
    ("0#STXE*.EX", "Eurex EURO STOXX 50 Index Option Chain Contracts"),
]


def test_ric_root():
    assert [ric_root(r) for r in (".SPX", "SPY.P", "AAPL.O", ".STOXX50E")] == ["SPX", "SPY", "AAPL", "STOXX50E"]


def test_root_named_chain_is_preferred_and_noise_dropped():
    picked = pick_chains(".SPX", SPX_ROWS)
    assert [c.chain_ric for c in picked] == ["0#SPX*.U", "0#SPXW*.U", "0#SPXO*.U"]
    assert [c.preferred for c in picked] == [True, False, False]


def test_single_whole_chain_is_preferred_when_root_differs():
    picked = pick_chains(".STOXX50E", STOXX_ROWS)
    assert [c.chain_ric for c in picked] == ["0#STXE*.EX", "0#STXE5W*.EX"]
    assert picked[0].preferred and not picked[1].preferred


def test_main_chain_preferred_over_session_and_weekly_variants():
    rows = [
        ("0#JNI*.OS", "Osaka Exchange NIKKEI 225 Full Session Index Option Chain Chain Contracts"),
        ("0#1JNI*.OS", "Osaka Securities Exchange NIKKEI 225 Night Session Index Option Chain Contract"),
        ("0#JNMW4W*.OS", "Osaka Exchange Nikkei 225 Wednesday 4W Full Session Index Option Chain Chain Contracts"),
        ("0#2JNMW3W*.OS", "Osaka Exchange Nikkei 225 Wednesday 3W Day Session Index Option Chain Chain Contracts"),
        ("0#JNMWL1W*.OS", "Osaka Exchange Nikkei 225 Wednesday 1W J-NET Session Index Option Chain Chain Contracts"),
        ("0#JNI1W*.OS", "Osaka Exchange Nikkei 225 Weekly (1W) Full Session Index Option Chain Chain Contracts"),
        ("0#JNML1W*.OS", "Osaka Exchange Nikkei 225 Micro Weekly (1W) J-NET Session Index Option Chain Chain Contracts"),
    ]
    got = pick_chains(".N225", rows)
    assert [c.chain_ric for c in got if c.preferred] == ["0#JNI*.OS"]
    assert got[0].chain_ric == "0#JNI*.OS"


def test_no_preference_when_ambiguous():
    rows = [("0#ABC*.U", "OPRA ABC Option Chain"), ("0#ABD*.U", "OPRA ABD Option Chain")]
    assert not any(c.preferred for c in pick_chains("XYZ.O", rows))


def test_third_friday():
    assert third_friday(2026, 11) == date(2026, 11, 20)
    assert third_friday(2027, 1) == date(2027, 1, 15)


def test_monthly_filter_keeps_third_fridays_and_holiday_thursdays():
    listed = [date(2026, 11, 13), date(2026, 11, 20), date(2026, 11, 27), date(2026, 12, 18),
              date(2027, 3, 18)]                       # 2027-03-19 not listed -> Thursday stands in
    assert monthly_expiries(listed) == {date(2026, 11, 20), date(2026, 12, 18), date(2027, 3, 18)}
    uni = pd.DataFrame({"EXPIR_DATE": pd.to_datetime(listed), "STRIKE_PRC": range(5)})
    assert len(filter_expiries(uni, "monthly")) == 3 and len(filter_expiries(uni, "all")) == 5


def test_summarise_chain():
    uni = pd.DataFrame({
        "EXPIR_DATE": pd.to_datetime(["2026-11-20", "2026-11-20", "2027-12-17"]),
        "STRIKE_PRC": [90.0, 110.0, 150.0],
        "UNDERLYING": ["SPY", "SPY", "IVV"],
    })
    c = summarise("SPY.P", "0#SPY*.U", uni)
    assert (c.n_options, c.n_expiries, c.first_expiry, c.last_expiry) == (3, 2, date(2026, 11, 20), date(2027, 12, 17))
    assert (c.strike_min, c.strike_max) == (90.0, 150.0)
    assert abs(c.underlying_match - 2 / 3) < 1e-12
