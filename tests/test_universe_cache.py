"""UniverseCache: an unreadable or unwritable cache file never fails a snapshot."""
from __future__ import annotations

import pandas as pd

from vol_fitter.snapshot.universe_cache import UniverseCache

_ROWS = pd.DataFrame({
    "Instrument": ["ABC1.U", "ABC2.U"], "STRIKE_PRC": [100.0, 100.0],
    "EXPIR_DATE": ["2099-01-16", "2099-01-16"], "PUTCALLIND": ["CALL", "PUT "], "UNDERLYING": ["ABC", "ABC"],
})


class _FakeClient:
    def __init__(self):
        self.builds = 0

    def expand_chain(self, chain_ric):
        self.builds += 1
        return list(_ROWS["Instrument"])

    def get_with_retry(self, rics, fields):
        return _ROWS.copy()


def _cache(tmp_path, client):
    return UniverseCache(client, "0#ABC*.U", name="ABC", cache_dir=tmp_path / "cache")


def test_build_creates_cache_dir_and_reuses_file(tmp_path):
    client = _FakeClient()
    assert len(_cache(tmp_path, client).load()) == 2
    assert len(_cache(tmp_path, client).load()) == 2
    assert client.builds == 1
    assert len(list((tmp_path / "cache").glob("universe_*.csv"))) == 1


def test_unreadable_cache_file_falls_back_to_rebuild(tmp_path, monkeypatch):
    client = _FakeClient()
    _cache(tmp_path, client).load()

    def locked(*args, **kwargs):
        raise OSError(22, "Invalid argument")
    monkeypatch.setattr(pd, "read_csv", locked)
    universe = _cache(tmp_path, client).load()
    assert len(universe) == 2 and client.builds == 2


def test_unwritable_cache_dir_still_returns_universe(tmp_path, monkeypatch):
    client = _FakeClient()

    def locked(*args, **kwargs):
        raise OSError(22, "Invalid argument")
    monkeypatch.setattr(pd.DataFrame, "to_csv", locked)
    universe = _cache(tmp_path, client).load()
    assert universe["is_call"].tolist() == [True, False]
