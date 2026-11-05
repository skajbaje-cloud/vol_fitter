"""Create the vol_fitter MySQL database (if missing) and all tables.

Run directly: python -m vol_fitter.db.init_db
Requires a .env with real MySQL credentials already in place (see .env.example).
"""
from __future__ import annotations

from sqlalchemy import text

from vol_fitter import config
from vol_fitter.db.engine import build_engine, build_server_engine
from vol_fitter.db.schema import metadata
from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)


def create_database_if_missing(cfg: config.MySQLConfig | None = None) -> None:
    cfg = cfg or config.MySQLConfig.from_env()
    server_engine = build_server_engine(cfg)
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{cfg.database}`"))
        conn.commit()
    logger.info("Database '%s' ready on %s:%s", cfg.database, cfg.host, cfg.port)


def create_tables(cfg: config.MySQLConfig | None = None) -> None:
    cfg = cfg or config.MySQLConfig.from_env()
    engine = build_engine(cfg)
    metadata.create_all(engine)
    logger.info("All tables created/verified in '%s'", cfg.database)


def init_db() -> None:
    cfg = config.MySQLConfig.from_env()
    create_database_if_missing(cfg)
    create_tables(cfg)


if __name__ == "__main__":
    init_db()
