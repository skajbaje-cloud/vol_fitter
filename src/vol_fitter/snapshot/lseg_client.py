"""Thin wrapper around lseg.data: session lifecycle, retries, chain expansion."""
from __future__ import annotations

import time

import pandas as pd

from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)


class LsegClient:
    def __init__(self, tries: int = 4, backoff_base: float = 2.0):
        self.tries = tries
        self.backoff_base = backoff_base
        self._ld = None

    def __enter__(self) -> "LsegClient":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        import lseg.data as ld

        self._ld = ld
        self._ld.open_session()
        logger.info("LSEG session opened")

    def close(self) -> None:
        if self._ld is not None:
            self._ld.close_session()
            logger.info("LSEG session closed")

    def expand_chain(self, chain_ric: str) -> list[str]:
        from lseg.data.discovery import Chain

        out: list[str] = []
        for ric in Chain(name=chain_ric).constituents:
            out.extend(self.expand_chain(ric) if ric.startswith("0#") else [ric])
        return out

    def get_with_retry(self, rics: list[str], fields: list[str]) -> pd.DataFrame:
        last_exc: Exception | None = None
        for attempt in range(self.tries):
            try:
                return self._ld.get_data(universe=rics, fields=fields)
            except Exception as exc:  # LSEG client raises various transient errors
                last_exc = exc
                if attempt == self.tries - 1:
                    break
                wait = self.backoff_base**attempt
                logger.warning("get_data failed (attempt %d/%d): %s; retrying in %.0fs",
                                attempt + 1, self.tries, exc, wait)
                time.sleep(wait)
        logger.error("get_data failed after %d attempts", self.tries)
        raise last_exc
