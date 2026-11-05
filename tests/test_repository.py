"""DB round-trip tests against a real local MySQL instance.

Run against a disposable `<db>_test` database (created/dropped around the
module), never the real `vol_fitter` database. Skipped automatically if
MySQL isn't reachable or `.env` isn't configured yet.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pandas as pd
import pytest

from vol_fitter import config
from vol_fitter.db.engine import build_engine
from vol_fitter.db.init_db import create_database_if_missing, create_tables
from vol_fitter.db.models import NameRecord, SnapshotRecord
from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.db.schema import metadata


@pytest.fixture(scope="module")
def repo():
    cfg = config.MySQLConfig.from_env()
    test_cfg = replace(cfg, database=f"{cfg.database}_test")
    try:
        create_database_if_missing(test_cfg)
        create_tables(test_cfg)
    except Exception as exc:  # any connection/auth failure -> skip, don't fail the suite
        pytest.skip(f"MySQL not reachable with current .env config: {exc}")

    engine = build_engine(test_cfg)
    yield VolFitterRepository(engine)
    metadata.drop_all(engine)


def test_get_or_create_name_id_is_idempotent(repo):
    first = repo.get_or_create_name_id(NameRecord(name="TEST.NAME", chain_ric="0#TEST*.EX"))
    second = repo.get_or_create_name_id(NameRecord(name="TEST.NAME"))
    assert first == second


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
