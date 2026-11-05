"""SQLAlchemy engine construction from config."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from vol_fitter import config
from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)


def _url(cfg: config.MySQLConfig, database: str | None = None) -> str:
    db = database if database is not None else cfg.database
    return (
        f"mysql+pymysql://{cfg.user}:{cfg.password}@{cfg.host}:{cfg.port}/{db}"
    )


def build_engine(cfg: config.MySQLConfig | None = None, *, echo: bool = False) -> Engine:
    """Engine bound to the configured vol_fitter database."""
    cfg = cfg or config.MySQLConfig.from_env()
    logger.debug("Building MySQL engine host=%s db=%s", cfg.host, cfg.database)
    return create_engine(_url(cfg), echo=echo, pool_pre_ping=True)


def build_server_engine(cfg: config.MySQLConfig | None = None, *, echo: bool = False) -> Engine:
    """Engine with no default database selected — used to create the database itself."""
    cfg = cfg or config.MySQLConfig.from_env()
    return create_engine(_url(cfg, database=""), echo=echo, pool_pre_ping=True)
