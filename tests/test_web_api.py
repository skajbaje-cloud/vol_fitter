"""HTTP API tests: real routes over the `<db>_test` database, with a fake snapshot runner
standing in for LSEG (no live market data is touched)."""
from __future__ import annotations

import time
from datetime import date, datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from vol_fitter.db.models import NameRecord, SnapshotRecord
from vol_fitter.orchestration.models import ExpiryFitSummary, FitRunResult, SnapshotRunResult
from vol_fitter.snapshot.models import ChainCandidate, ChainCheck, NameLookupResult
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


def _fake_snapshot(p: dict) -> SnapshotRunResult:
    return SnapshotRunResult(name=p["name"], snapshot_ts=NEW_TS, spot=100.0, window_vol=0.14, universe_size=10,
                             window_size=4, n_quotes=2, n_maturities=2, duration_sec=0.01)


def _fake_lookup(p: dict) -> list[NameLookupResult]:
    return [NameLookupResult(ric=r, found=r != "BAD.X", display_name=f"{r} Inc", spot=50.0, currency="USD", vol=0.2,
                             candidates=[ChainCandidate(f"0#{r.split('.')[0]}*.U", "OPRA Option Chain", True)])
            for r in p["rics"]]


def _fake_check(p: dict) -> ChainCheck:
    return ChainCheck(name=p["name"], chain_ric=p["chain_ric"], n_options=120, n_expiries=6,
                      first_expiry=date(2027, 3, 19), last_expiry=date(2028, 12, 15),
                      strike_min=50.0, strike_max=150.0, underlying_match=1.0, duration_sec=0.01)


def _fake_fit(p: dict) -> list[FitRunResult]:
    exp = [ExpiryFitSummary(expiry_date=e, status="ok" if i == 0 else "failed", params=(0.2, 0.0, 0.0, 0.0), n_quotes=10,
                            pct_inside=0.9 - 0.4 * i, n_outliers=i, n_model_miss=0, anchor_snapshot_ts=None, anchor_lambda=0.0)
           for i, e in enumerate(EXPIRIES)]
    return [FitRunResult(name=p["name"], snapshot_ts=NEW_TS, expiries=exp, n_quotes=20, duration_sec=0.5)]


@pytest.fixture(scope="module")
def client(repo, seeded, tmp_path_factory):
    dist = tmp_path_factory.mktemp("dist")
    (dist / "index.html").write_text("<title>Vol Surface Console</title>")
    app = create_app(runners={"snapshot": _fake_snapshot, "lookup": _fake_lookup, "check": _fake_check, "fit": _fake_fit},
                     frontend_dist=dist)
    app.dependency_overrides[get_repo] = lambda: repo
    with TestClient(app) as c:
        yield c


def test_names_snapshots_and_maturities(client):
    web_a = next(n for n in client.get("/api/names").json() if n["name"] == "WEB.A")
    assert web_a["last_snapshot_ts"] == NEW_TS.isoformat() and web_a["expiry_filter"] == "all"
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
    # forward call-equivalent delta: put -0.5/0.99 -> 1 - 0.505; call 0.5/0.99
    assert body["quotes"]["fwd_delta"] == [pytest.approx(1 - 0.5 / 0.99), pytest.approx(0.5 / 0.99)]
    assert body["h_min"] == pytest.approx(0.0025) and body["params"]["fit_status"] is None


def test_unknown_name_and_missing_smile_are_404(client):
    assert client.get("/api/names/NOPE/snapshots").status_code == 404
    r = client.get("/api/smile", params={"name": "WEB.A", "snapshot_ts": NEW_TS.isoformat(), "expiry": "2030-01-01"})
    assert r.status_code == 404


def _wait_done(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} didn't finish")


def test_snapshot_jobs_run_to_done(client):
    r = client.post("/api/snapshots/run", json={"names": ["WEB.A"]})
    assert r.status_code == 202
    job = _wait_done(client, r.json()[0]["id"])
    assert job["status"] == "done" and job["n_quotes"] == 2 and job["window_vol"] == pytest.approx(0.14)


def test_snapshot_of_unregistered_name_is_rejected(client):
    r = client.post("/api/snapshots/run", json={"names": ["WEB.A", "NEW.ONE"]})
    assert r.status_code == 400 and "NEW.ONE" in r.json()["detail"]


def test_register_then_edit_a_name(client):
    body = [{"name": "WEB.NEW", "chain_ric": "0#WEBN*.U", "display_name": "Web New", "group_name": "Test",
             "expiry_filter": "monthly"}]
    r = client.post("/api/names", json=body)
    assert r.status_code == 201 and r.json()[0]["group_name"] == "Test" and r.json()[0]["last_snapshot_ts"] is None
    assert client.post("/api/names", json=body).status_code == 409          # never silently overwritten
    r = client.patch("/api/names/WEB.NEW", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["expiry_filter"] == "monthly"
    assert client.patch("/api/names/NOPE.X", json={"active": False}).status_code == 404
    assert client.patch("/api/names/WEB.NEW", json={"expiry_filter": "weekly"}).status_code == 422


def test_register_rejects_ric_with_quotes(client):
    r = client.post("/api/names", json=[{"name": "BAD'X", "chain_ric": "0#X*.U"}])
    assert r.status_code == 422


def test_lookup_job_returns_candidates_and_registered_flag(client):
    r = client.post("/api/names/lookup", json={"rics": ["WEB.A", " AAPL.O ", "AAPL.O"]})
    assert r.status_code == 202
    job = _wait_done(client, r.json()["id"])
    rows = {x["ric"]: x for x in job["lookup"]}
    assert list(rows) == ["WEB.A", "AAPL.O"]                                # trimmed and de-duplicated
    assert rows["WEB.A"]["registered"] and not rows["AAPL.O"]["registered"]
    assert rows["AAPL.O"]["candidates"][0] == {"chain_ric": "0#AAPL*.U", "title": "OPRA Option Chain", "preferred": True}
    assert client.post("/api/names/lookup", json={"rics": ["AAPL O'"]}).status_code == 400


def test_chain_check_job(client):
    r = client.post("/api/names/check", json={"name": "AAPL.O", "chain_ric": "0#AAPL*.U"})
    job = _wait_done(client, r.json()["id"])
    assert job["kind"] == "check" and job["check"]["n_options"] == 120 and job["check"]["last_expiry"] == "2028-12-15"


def test_frontend_served_at_root(client):
    assert "Vol Surface Console" in client.get("/").text


# ---- snapshot schedule ----

def test_schedule_save_and_read_back(client):
    client.post("/api/names", json=[{"name": "SCHW.A", "chain_ric": "0#SCHWA*.U", "timezone": "America/New_York"}])
    r = client.put("/api/schedule", json={"items": [
        {"name": "SCHW.A", "times": ["15:45", "09:45"], "days": ["Mon", "Wed"], "enabled": True}]})
    assert r.status_code == 200, r.text
    row = next(n for n in r.json()["names"] if n["name"] == "SCHW.A")
    assert row["times"] == ["09:45", "15:45"] and row["days"] == ["Mon", "Wed"] and row["timezone"] == "America/New_York"
    assert row["next_fire_label"] in ("09:45 EST", "15:45 EST", "09:45 EDT", "15:45 EDT")
    again = next(n for n in client.get("/api/schedule").json()["names"] if n["name"] == "SCHW.A")
    assert again["times"] == ["09:45", "15:45"]


def test_schedule_validation(client):
    client.post("/api/names", json=[{"name": "SCHW.B", "chain_ric": "0#SCHWB*.U"}])      # no time zone
    put = lambda item: client.put("/api/schedule", json={"items": [item]}).status_code  # noqa: E731
    assert put({"name": "SCHW.A", "times": ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00"]}) == 422
    assert put({"name": "SCHW.A", "times": ["9:45"]}) == 422
    assert put({"name": "SCHW.A", "times": ["24:00"]}) == 422
    assert put({"name": "SCHW.A", "times": ["09:45", "09:45"]}) == 422
    assert put({"name": "SCHW.A", "times": ["09:45"], "days": ["Funday"]}) == 422
    assert put({"name": "NOPE.X", "times": ["09:45"]}) == 404
    assert put({"name": "SCHW.B", "times": ["09:45"]}) == 422
    assert put({"name": "SCHW.B", "times": []}) == 200            # clearing needs no zone


def test_timezone_patch_is_validated(client):
    assert client.patch("/api/names/SCHW.B", json={"timezone": "Mars/Olympus"}).status_code == 422
    r = client.patch("/api/names/SCHW.B", json={"timezone": "Europe/London"})
    assert r.status_code == 200 and r.json()["timezone"] == "Europe/London"


def test_pause_persists_and_status_lists_upcoming(client):
    r = client.post("/api/scheduler/pause", json={"paused": True})
    assert r.status_code == 200 and r.json()["paused"] is True
    status = client.get("/api/scheduler/status").json()
    assert status["paused"] is True and status["enabled"] is False     # tests never start the thread
    assert client.get("/api/schedule").json()["paused"] is True
    client.post("/api/scheduler/pause", json={"paused": False})
    assert client.get("/api/scheduler/status").json()["paused"] is False


def test_lookup_returns_timezone_guess_and_jobs_carry_origin(client):
    job = client.post("/api/names/lookup", json={"rics": ["XYZ.P"]}).json()
    _wait_done(client, job["id"])
    done = client.get(f"/api/jobs/{job['id']}").json()
    assert done["lookup"][0]["timezone_guess"] == "America/New_York"
    assert done["origin"] == "manual"


# ---- fits ----

def test_fit_job_runs_on_its_own_queue_and_summarises(client):
    jobs = client.post("/api/fits/run", json={"names": ["WEB.A"], "mode": "latest"}).json()
    assert len(jobs) == 1 and jobs[0]["kind"] == "fit"
    _wait_done(client, jobs[0]["id"])
    done = client.get(f"/api/jobs/{jobs[0]['id']}").json()
    assert done["status"] == "done" and done["duration_sec"] == pytest.approx(0.5)
    s = done["fit"][0]
    assert s["n_expiries"] == 2 and s["n_ok"] == 1 and s["min_pct_inside"] == pytest.approx(0.5)
    assert s["mean_pct_inside"] == pytest.approx(0.7) and s["n_outliers"] == 1
    ids = [j["id"] for j in client.get("/api/jobs").json()]
    assert jobs[0]["id"] in ids and len(ids) == len(set(ids))        # one list, unique ids across both queues


def test_fit_run_validation(client):
    assert client.post("/api/fits/run", json={"names": ["NOPE.X"]}).status_code == 400
    assert client.post("/api/fits/run", json={"names": ["WEB.A"], "mode": "snapshot"}).status_code == 422
    assert client.post("/api/fits/run", json={"names": ["WEB.A"], "mode": "bogus"}).status_code == 422
    ok = client.post("/api/fits/run", json={"names": ["WEB.A"], "mode": "snapshot", "snapshot_ts": NEW_TS.isoformat()})
    assert ok.status_code == 202


def test_fit_coverage_and_expiry_detail(client):
    cov = [c for c in client.get("/api/fits/coverage").json() if c["name"] == "WEB.A"]
    assert [c["snapshot_ts"] for c in cov] == [NEW_TS.isoformat(), OLD_TS.isoformat()]
    assert cov[0]["n_expiries"] == 2 and cov[0]["n_fitted"] == 0 and cov[0]["mean_pct_inside"] is None
    rows = client.get(f"/api/fits/WEB.A/{NEW_TS.isoformat()}").json()
    assert [r["expiry_date"] for r in rows] == [e.isoformat() for e in EXPIRIES]
    assert rows[0]["forward"] == pytest.approx(100.5) and rows[0]["fit_status"] is None
    assert client.get("/api/fits/WEB.A/2020-01-01T00:00:00").status_code == 404


def test_spline_study_endpoint(client):
    r = client.get(f"/api/spline/WEB.A/{NEW_TS.isoformat()}")
    assert r.status_code == 200
    body = r.json()
    assert [e["expiry"] for e in body] == [str(e) for e in EXPIRIES]
    assert body[0]["status"] == "too_few" and body[0]["points"]["strike"] == [95.0, 105.0]
    assert client.get(f"/api/spline/NOPE/{NEW_TS.isoformat()}").status_code == 404
