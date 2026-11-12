"""Best-guess IANA time zone for a RIC, used to pre-fill names.timezone (always editable)."""
from __future__ import annotations

from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)

NEW_YORK, BERLIN, LONDON = "America/New_York", "Europe/Berlin", "Europe/London"

_INDEX_ZONES = {
    ".SPX": NEW_YORK, ".NDX": NEW_YORK, ".RUT": NEW_YORK, ".DJI": NEW_YORK, ".VIX": NEW_YORK, ".XSP": NEW_YORK,
    ".STOXX50E": BERLIN, ".GDAXI": BERLIN, ".FCHI": "Europe/Paris", ".AEX": "Europe/Amsterdam",
    ".FTSE": LONDON, ".N225": "Asia/Tokyo", ".HSI": "Asia/Hong_Kong",
}

# Exchange suffix -> zone. US venues share New York time.
_SUFFIX_ZONES = {
    "N": NEW_YORK, "O": NEW_YORK, "OQ": NEW_YORK, "P": NEW_YORK, "K": NEW_YORK, "A": NEW_YORK, "Z": NEW_YORK,
    "L": LONDON, "DE": BERLIN, "F": BERLIN, "PA": "Europe/Paris", "AS": "Europe/Amsterdam",
    "MI": "Europe/Rome", "MC": "Europe/Madrid", "SW": "Europe/Zurich", "T": "Asia/Tokyo", "HK": "Asia/Hong_Kong",
}


def guess_timezone(ric: str) -> str | None:
    """Zone for a RIC, or None when it can't be told from the RIC alone."""
    ric = (ric or "").strip()
    if not ric:
        return None
    if ric.startswith("."):
        return _INDEX_ZONES.get(ric.upper())
    if "." not in ric:
        return NEW_YORK                      # US composite RICs (SPY, QQQ) carry no venue suffix
    return _SUFFIX_ZONES.get(ric.rsplit(".", 1)[1].upper())
