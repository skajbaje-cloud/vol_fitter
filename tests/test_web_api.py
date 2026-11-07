"""HTTP API tests: real routes over the `<db>_test` database, with a fake snapshot runner
standing in for LSEG (no live market data is touched)."""
from __future__ import annotations

import time
from datetime import date, datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from vol_fitter.db.models import NameRecord, SnapshotRecord
from vol_fitter.orchestration.models import SnapshotRunResult
from vol_fitter.web.app import create_app
from vol_fitter.web.deps import get_repo

OLD_TS, NEW_TS = datetime(2027, 2, 1, 10, 0, 0), datetime(2027, 2, 2, 10, 0, 0)
EXPIRIES = [date(2027, 3, 19), date(2027, 6, 18)]


def _quote(name_id, ts, expiry, strike, is_call, bid_iv):
    return {
        "name_id": name_id, "snapshot_ts": ts, "instrument": f"X{strike}{'C' if is_call else 'P'}{expiry:%m%y}",
        "strike": strike, "expiry_date": expiry, "T": 0.2, "is_call": is_call, "bid": 1.0, "ask": 1.1,
        "bid_iv": bid_iv, "ask_iv": 0.21, "bid_delta": 0.5 if is_call else -0.5, "ask_delta": 0.5 if is_call else -0.5,
    }


@pytest.fixture(scope="module")
def seeded(repo):
    name_id = repo.get_or_create_name_id(NameRecord(name="WEB.A", chain_ric="0#WEBA*.X"))
    for ts in (OLD_TS, NEW_TS):
        repo.upsert_snapshot(SnapshotRecord(name_id=name_id, snapshot_ts=ts, spot=100.0, universe_size=10, window_size=4))
        repo.upsert_maturity_params(pd.DataFrame([
            {"name_id": name_id, "snapshot_ts": ts, "expiry_date": e, "T": 0.2, "forward": 100.5, "discount_factor": 0.99}
            for e in EXPIRIES
        ]))
        repo.insert_quotes(pd.DataFrame([
            _quote(name_id, ts, EXPIRIES[0], 95.0, False, 0.22),
            _quote(name_id, ts, EXPIRIES[0], 105.0, True, float("nan")),
        ]))
    return name_id


def _fake_runner(name: str, chain_ric: str | None) -> SnapshotRunResult:
    return SnapshotRunResult(name=name, snapshot_ts=NEW_TS, spot=100.0, window_vol=0.14, universe_size=10,
                             window_size=4, n_quotes=2, n_maturities=2, duration_sec=0.01)


@pytest.fixture(scope="module")
def client(repo, seeded, tmp_path_factory):
    dist = tmp_path_factory.mktemp("dist")
    (dist / "index.html").write_text("<title>Vol Surface Console</title>")
    app = create_app(runner=_fake_runner, frontend_dist=dist)
    app.dependency_overrides[get_repo] = lambda: repo
    with TestClient(app) as c:
        yield c


def test_names_snapshots_and_maturities(client):
    assert "WEB.A" in [n["name"] for n in client.get("/api/names").json()]
    assert client.get("/api/names/WEB.A/snapshots").json() == [NEW_TS.isoformat(), OLD_TS.isoformat()]
    mats = client.get(f"/api/names/WEB.A/snapshots/{NEW_TS.isoformat()}/maturities").json()
    assert mats == [e.isoformat() for e in EXPIRIES]


def test_smile_returns_quotes_and_params_with_nulls(client):
    r = client.get("/api/smile", params={"name": "WEB.A", "snapshot_ts": NEW_TS.isoformat(), "expiry": "2027-03-19"})
    assert r.status_code == 200
    body = r.json()
    assert body["spot"] == 100.0 and body["params"]["forward"] == pytest.approx(100.5)
    assert body["params"]["sigma_atm"] is None
    assert body["quotes"]["strike"] == [95.0, 105.0]
    assert body["quotes"]["is_call"] == [False, True]
    assert body["quotes"]["bid_iv"] == [pytest.approx(0.22), None]  # NULL stays null, never NaN


def test_unknown_name_and_missing_smile_are_404(client):
    assert client.get("/api/names/NOPE/snapshots").status_code == 404
    r = client.get("/api/smile", params={"name": "WEB.A", "snapshot_ts": NEW_TS.isoformat(), "expiry": "2030-01-01"})
    assert r.status_code == 404


def _wait_done(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = next(j for j in client.get("/api/jobs").json() if j["id"] == job_id)
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} didn't finish")


def test_single_snapshot_job_runs_to_done(client):
    r = client.post("/api/snapshots/run", json={"scope": "single", "underlying": "WEB.A"})
    assert r.status_code == 202
    job = _wait_done(client, r.json()[0]["id"])
    assert job["status"] == "done" and job["n_quotes"] == 2 and job["window_vol"] == pytest.approx(0.14)


def test_universe_scope_queues_every_active_name(client, repo):
    r = client.post("/api/snapshots/run", json={"scope": "universe"})
    assert {j["name"] for j in r.json()} == {n.name for n in repo.list_names(active_only=True)}


def test_unregistered_name_needs_a_chain_ric(client):
    r = client.post("/api/snapshots/run", json={"scope": "single", "underlying": "NEW.ONE"})
    assert r.status_code == 400 and "chain RIC" in r.json()["detail"]


def test_frontend_served_at_root(client):
    assert "Vol Surface Console" in client.get("/").text
