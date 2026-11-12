from vol_fitter.scheduling.tz_guess import guess_timezone


def test_guesses():
    assert guess_timezone(".SPX") == "America/New_York"
    assert guess_timezone(".STOXX50E") == "Europe/Berlin"
    assert guess_timezone("SPY") == "America/New_York"
    assert guess_timezone("XLK.P") == "America/New_York"
    assert guess_timezone("AAPL.O") == "America/New_York"
    assert guess_timezone("BRKb.N") == "America/New_York"
    assert guess_timezone("VOD.L") == "Europe/London"
    assert guess_timezone("SAPG.DE") == "Europe/Berlin"
    assert guess_timezone(".UNKNOWNIDX") is None
    assert guess_timezone("ABC.XYZ") is None
    assert guess_timezone("") is None
