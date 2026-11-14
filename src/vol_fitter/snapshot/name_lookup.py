"""Look up a typed underlying RIC in LSEG: name, spot, vol, and candidate option chains.

Nothing here touches the database; the result is shown to the user to confirm.
Chains are found with LSEG search (fast), not by expanding them (slow for big
chains -- see chain_check.py). ETF options report the composite RIC (`SPY`,
not `SPY.P`) as their underlying, so both the typed RIC and its root are searched.
"""
from __future__ import annotations

import re

import pandas as pd

from vol_fitter import config
from vol_fitter.logging_setup import get_logger
from vol_fitter.snapshot.lseg_client import LsegClient
from vol_fitter.snapshot.models import ChainCandidate, NameLookupResult

logger = get_logger(__name__)

_INFO_FIELDS = ["CF_NAME", "CF_LAST", "CF_CURR", "TR.CommonName", config.VOL_FIELD]
_EXCLUDE = ("binary", "atm chain", "volatility surface", "spread", "future")
# Side chains next to the main one: short-dated series and out-of-hours sessions (Osaka lists all of these).
_VARIANTS = ("weekly", "wednesday", "night session", "day session", "j-net", "micro", "mini")
_PER_EXPIRY = re.compile(r"[FGHJKMNQUVXZ]\d\d\*")   # e.g. 0#STXEZ26*.EX: one expiry's sub-chain
_SEARCH_TOP = 25
_UNRESOLVED = re.compile(r"resolve|invalid|not found|unknown", re.IGNORECASE)   # LSEG's errors for a bad RIC


def ric_root(ric: str) -> str:
    """'.SPX' -> 'SPX', 'SPY.P' -> 'SPY', 'AAPL.O' -> 'AAPL'."""
    return ric.lstrip(".").split(".")[0]


def pick_chains(ric: str, rows: list[tuple[str, str]]) -> list[ChainCandidate]:
    """Filter search hits down to listed-option chains and rank them, best first.

    Preferred: the chain named after the RIC's root (0#AAPL*.U); failing that,
    the single remaining whole-chain candidate that isn't a variant (weekly,
    night/day/J-NET session, mini/micro) -- e.g. 0#JNI*.OS for .N225.
    """
    root = ric_root(ric).upper()
    keep: dict[str, str] = {}
    for chain, title in rows:
        t = (title or "").lower()
        if not chain.startswith("0#") or "option chain" not in t or any(x in t for x in _EXCLUDE):
            continue
        if _PER_EXPIRY.search(chain):
            continue
        keep.setdefault(chain, title)

    def exact(chain: str) -> bool:
        return re.fullmatch(rf"0#{re.escape(root)}\*\.[A-Z]+", chain.upper()) is not None

    def variant(title: str) -> bool:
        return any(x in title.lower() for x in _VARIANTS)

    ranked = sorted(keep.items(), key=lambda kv: (not exact(kv[0]), variant(kv[1]), len(kv[0]), kv[0]))
    whole = [c for c, t in ranked if not variant(t)]
    best = next((c for c, _ in ranked if exact(c)), whole[0] if len(whole) == 1 else None)
    return [ChainCandidate(chain_ric=c, title=t, preferred=(c == best)) for c, t in ranked]


class NameLookup:
    def __init__(self, client: LsegClient):
        self.client = client

    def lookup(self, rics: list[str]) -> list[NameLookupResult]:
        info = self._info(rics)
        return [self._one(ric, info.get(ric, {})) for ric in rics]

    def _one(self, ric: str, info: dict) -> NameLookupResult:
        name = info.get("name")
        spot = info.get("spot")
        if name is None and spot is None:
            return NameLookupResult(ric=ric, found=False, error="LSEG doesn't recognise this RIC.")
        try:
            candidates = pick_chains(ric, self._search_chains(ric))
            error = None if candidates else "No listed-option chain found; type one in."
        except Exception as exc:  # search outages shouldn't hide the instrument info
            logger.warning("chain search failed for %s: %s", ric, exc)
            candidates, error = [], f"Chain search failed: {exc}"
        return NameLookupResult(
            ric=ric, found=True, display_name=name, spot=spot, currency=info.get("currency"),
            vol=info.get("vol"), candidates=candidates, error=error,
        )

    def _search_chains(self, ric: str) -> list[tuple[str, str]]:
        under = " or ".join(f"UnderlyingQuoteRIC eq '{u}'" for u in dict.fromkeys([ric, ric_root(ric)]))
        df = self.client.search(filter=f"({under}) and IsChain eq true", select="RIC,DocumentTitle", top=_SEARCH_TOP)
        if df is None or df.empty:
            # Some names (BRKb.N) carry no underlying link; try the usual chain names for the root.
            root = ric_root(ric).upper()
            names = " or ".join(f"RIC eq '0#{root}*.{x}'" for x in ("U", "EX"))
            df = self.client.search(filter=names, select="RIC,DocumentTitle", top=_SEARCH_TOP)
        if df is None or df.empty:
            return []
        return list(zip(df["RIC"].astype(str), df["DocumentTitle"].astype(str)))

    def _info(self, rics: list[str]) -> dict[str, dict]:
        try:
            df = self.client.get_with_retry(rics, _INFO_FIELDS)
        except Exception as exc:
            logger.warning("info batch failed (%s); retrying one RIC at a time", exc)
            frames, errors = [], []
            for r in rics:
                try:
                    frames.append(self.client.get_with_retry([r], _INFO_FIELDS))
                except Exception as one:
                    logger.warning("no info for %s: %s", r, one)
                    errors.append(one)
            # An unknown RIC fails to resolve; anything else (timeouts, closed session) means LSEG itself is down,
            # which must not be reported as "doesn't recognise this RIC".
            outage = [e for e in errors if not _UNRESOLVED.search(str(e))]
            if not frames and outage:
                raise RuntimeError(f"LSEG request failed, so nothing was looked up: {outage[-1]}") from outage[-1]
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        out: dict[str, dict] = {}
        for _, row in df.iterrows():
            ric = str(row["Instrument"])
            # An index's "company" is its publisher (STOXX AG), so indices use the quote name instead.
            order = ("CF_NAME", "Company Common Name") if ric.startswith(".") else ("Company Common Name", "CF_NAME")
            vol = _first(row, ("Volatility - 40 days", config.VOL_FIELD))
            out[ric] = {
                "name": _first(row, order),
                "spot": _num(_first(row, ("CF_LAST",))),
                "currency": _first(row, ("CF_CURR",)),
                "vol": None if _num(vol) is None else _num(vol) / 100.0,
            }
        return out


def _first(row: pd.Series, cols: tuple[str, ...]):
    for c in cols:
        if c in row.index and pd.notna(row[c]) and str(row[c]).strip():
            return row[c]
    return None


def _num(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None
