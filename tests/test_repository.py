"""DB round-trip tests against the disposable `<db>_test` MySQL database (see conftest.py)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from vol_fitter.db.models import NameRecord, SnapshotRecord

def test_get_or_create_name_id_is_idempotent_and_refreshes_fields(repo):
    first = repo.get_or_create_name_id(NameRecord(name="TEST.NAME", chain_ric="0#TEST*.EX"))
    second = repo.get_or_create_name_id(NameRecord(name="TEST.NAME", chain_ric="0#TEST2*.EX"))
    assert first == second

    fetched = repo.get_name("TEST.NAME")
    assert fetched.name_id == first
    assert fetched.chain_ric == "0#TEST2*.EX"


def test_get_name_returns_none_for_unknown_name(repo):
    assert repo.get_name("NOPE.UNKNOWN") is None


def test_snapshot_and_quotes_roundtrip(repo):
    name_id = repo.get_or_create_name_id(NameRecord(name="TEST.NAME2"))
    ts = datetime(2027, 1, 1, 12, 0, 0)

    repo.upsert_snapshot(SnapshotRecord(
        name_id=name_id, snapshot_ts=ts, spot=100.0,
        universe_size=10, window_size=5, snap_duration_sec=1.2, status="ok",
    ))

    df = pd.DataFrame([{
        "name_id": name_id, "snapshot_ts": ts, "instrument": "TESTX1",
        "strike": 100.0, "expiry_date": datetime(2027, 3, 1).date(), "T": 0.2,
        "is_call": True, "bid": 1.0, "ask": 1.2,
        "bid_iv": 0.20, "ask_iv": 0.21,
        "bid_delta": 0.50, "ask_delta": 0.52,
        "bid_gamma": 0.01, "ask_gamma": 0.01,
        "bid_vega": 0.10, "ask_vega": 0.10,
        "bid_theta": -0.05, "ask_theta": -0.05,
        "bid_rho": 0.02, "ask_rho": 0.02,
    }])
    n_inserted = repo.insert_quotes(df)
    assert n_inserted == 1

    fetched = repo.fetch_quotes(name_id, ts)
    assert len(fetched) == 1
    assert fetched.iloc[0]["instrument"] == "TESTX1"
    assert fetched.iloc[0]["bid_iv"] == pytest.approx(0.20)


def test_insert_quotes_handles_nan_as_null(repo):
    """Regression test: pymysql raises on a literal NaN ('nan can not be used
    with MySQL'); _upsert_df must convert NaN -> NULL before inserting."""
    name_id = repo.get_or_create_name_id(NameRecord(name="TEST.NAME4"))
    ts = datetime(2027, 1, 1, 12, 0, 0)

    df = pd.DataFrame([{
        "name_id": name_id, "snapshot_ts": ts, "instrument": "TESTX2",
        "strike": 100.0, "expiry_date": datetime(2027, 3, 1).date(), "T": 0.2,
        "is_call": True, "bid": 1.0, "ask": 1.2,
        "bid_iv": float("nan"), "ask_iv": 0.21,
        "bid_delta": float("nan"), "ask_delta": 0.52,
        "bid_gamma": float("nan"), "ask_gamma": 0.01,
        "bid_vega": 0.10, "ask_vega": 0.10,
        "bid_theta": -0.05, "ask_theta": -0.05,
        "bid_rho": 0.02, "ask_rho": 0.02,
    }])
    n_inserted = repo.insert_quotes(df)
    assert n_inserted == 1

    fetched = repo.fetch_quotes(name_id, ts)
    assert len(fetched) == 1
    assert pd.isna(fetched.iloc[0]["bid_iv"])
    assert fetched.iloc[0]["ask_iv"] == pytest.approx(0.21)


def test_maturity_params_upsert_overwrites_on_conflict(repo):
    name_id = repo.get_or_create_name_id(NameRecord(name="TEST.NAME3"))
    ts = datetime(2027, 1, 1, 12, 0, 0)
    expiry = datetime(2027, 3, 1).date()

    row = {
        "name_id": name_id, "snapshot_ts": ts, "expiry_date": expiry, "T": 0.2,
        "forward": 100.0, "discount_factor": 0.98,
        "n_strikes_forward": 5, "n_strikes_df": 15,
        "forward_fit_resid": 0.01, "df_fit_resid": 0.02,
    }
    repo.upsert_maturity_params(pd.DataFrame([row]))

    row["forward"] = 101.5
    repo.upsert_maturity_params(pd.DataFrame([row]))

    fetched = repo.fetch_maturity_params(name_id, ts)
    assert len(fetched) == 1
    assert fetched.iloc[0]["forward"] == pytest.approx(101.5)
