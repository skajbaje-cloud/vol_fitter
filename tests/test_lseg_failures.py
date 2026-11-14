"""LSEG failure handling: outages vs unknown RICs, closed sessions, prices returned as text (no LSEG needed)."""
import sys
import types

import pandas as pd
import pytest

from vol_fitter.snapshot.lseg_client import LsegClient, LsegUnavailableError
from vol_fitter.snapshot.name_lookup import NameLookup
from vol_fitter.snapshot.snapshot_service import SnapshotService


class _FailingClient:
    def __init__(self, message):
        self.message = message

    def get_with_retry(self, rics, fields):
        raise ValueError(self.message)


def test_lookup_outage_is_not_reported_as_unknown_ric():
    with pytest.raises(RuntimeError, match="LSEG request failed"):
        NameLookup(_FailingClient("Session is not opened. Can't send any request")).lookup([".HSCE", "AAPL.O"])


def test_lookup_unknown_ric_still_reported_per_ric():
    out = NameLookup(_FailingClient("Unable to resolve all requested identifiers")).lookup(["NOPE.X"])
    assert out[0].found is False and "recognise" in out[0].error


def test_closed_session_raises_clear_error(monkeypatch):
    closed = types.SimpleNamespace(open_state=types.SimpleNamespace(name="Closed"))
    fake = types.ModuleType("lseg.data")
    fake.open_session = lambda: closed
    fake.close_session = lambda: None
    monkeypatch.setitem(sys.modules, "lseg", types.ModuleType("lseg"))
    monkeypatch.setitem(sys.modules, "lseg.data", fake)
    with pytest.raises(LsegUnavailableError, match="Workspace isn't answering"):
        LsegClient().open()


class _Cache:
    def load(self):
        return pd.DataFrame({"Instrument": ["C1", "P1"], "STRIKE_PRC": [61000.0, 61000.0],
                             "EXPIR_DATE": pd.to_datetime(["2026-12-11"] * 2), "T": [0.08, 0.08], "is_call": [True, False]})


class _TextPricesClient:
    """Index with no last trade, option prices returned as strings (as Osaka does)."""
    def get_with_retry(self, rics, fields):
        if rics == [".N225"]:
            return pd.DataFrame({"Instrument": [".N225"], "TRDPRC_1": [pd.NA], "CF_LAST": [61000.0],
                                 "HST_CLOSE": [60900.0], "Volatility - 40 days": [25.0]})
        return pd.DataFrame({"Instrument": rics, "BID": [None, "1200", "1150"], "ASK": [None, "1250", "1190"],
                             "TRDPRC_1": [pd.NA, None, None]})


def test_text_prices_become_numbers_and_spot_falls_back():
    quotes, meta = SnapshotService(_TextPricesClient(), _Cache(), ".N225").snap()
    assert meta.spot == 61000.0
    assert quotes["bid"].tolist() == [1200.0, 1150.0] and pd.api.types.is_float_dtype(quotes["ask"])
    assert (0.5 * (quotes["bid"] + quotes["ask"])).tolist() == [1225.0, 1170.0]
