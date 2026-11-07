"""Shared fixture: a disposable `<db>_test` MySQL database, never the real one.

Created once per test session and dropped at the end. Tests that need it are
skipped automatically if MySQL isn't reachable or `.env` isn't configured.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from vol_fitter import config
from vol_fitter.db.engine import build_engine
from vol_fitter.db.init_db import create_database_if_missing, create_tables
from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.db.schema import metadata


@pytest.fixture(scope="session")
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
