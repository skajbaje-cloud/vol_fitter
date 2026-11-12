"""LSEG look-ups for adding names: shared by the web job queue (and usable from a REPL)."""
from __future__ import annotations

from vol_fitter.logging_setup import get_logger
from vol_fitter.snapshot.chain_check import ChainChecker
from vol_fitter.snapshot.lseg_client import LsegClient
from vol_fitter.snapshot.models import ChainCheck, NameLookupResult
from vol_fitter.snapshot.name_lookup import NameLookup

logger = get_logger(__name__)


def run_lookup(rics: list[str]) -> list[NameLookupResult]:
    """Instrument info plus ranked candidate chains for each RIC. Writes nothing."""
    with LsegClient() as client:
        return NameLookup(client).lookup(rics)


def run_chain_check(name: str, chain_ric: str) -> ChainCheck:
    """Expand one chain and summarise it; also warms the universe cache for the first snapshot."""
    with LsegClient() as client:
        return ChainChecker(client).check(name, chain_ric)
