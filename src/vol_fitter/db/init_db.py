"""Create the vol_fitter MySQL database (if missing) and all tables.

Run directly: python -m vol_fitter.db.init_db
Requires a .env with real MySQL credentials already in place (see .env.example).
"""
from __future__ import annotations

from sqlalchemy import inspect, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateColumn

from vol_fitter import config
from vol_fitter.db.engine import build_engine, build_server_engine
from vol_fitter.db.schema import metadata, names
from vol_fitter.logging_setup import get_logger
from vol_fitter.scheduling.tz_guess import guess_timezone

logger = get_logger(__name__)


def add_missing_columns(engine: Engine) -> list[str]:
    """Additive migration: ALTER TABLE ... ADD COLUMN for every schema column a live table lacks.

    create_all() only creates missing tables, never alters existing ones. This
    never drops or changes columns, so it's safe to run repeatedly.
    """
    added = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                ddl = CreateColumn(column).compile(dialect=engine.dialect)
                conn.execute(text(f"ALTER TABLE `{table.name}` ADD COLUMN {ddl}"))
                added.append(f"{table.name}.{column.name}")
    if added:
        logger.info("Added columns: %s", ", ".join(added))
    return added


def fill_missing_timezones(engine: Engine) -> list[str]:
    """Guess names.timezone from the RIC wherever it's still NULL; never overwrites a set zone."""
    filled = []
    with engine.begin() as conn:
        for row in conn.execute(select(names.c.name_id, names.c.name).where(names.c.timezone.is_(None))).all():
            zone = guess_timezone(row.name)
            if zone:
                conn.execute(update(names).where(names.c.name_id == row.name_id).values(timezone=zone))
                filled.append(f"{row.name}={zone}")
    if filled:
        logger.info("Guessed time zones: %s", ", ".join(filled))
    return filled


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
    add_missing_columns(engine)
    metadata.create_all(engine)
    fill_missing_timezones(engine)
    logger.info("All tables created/verified in '%s'", cfg.database)


def init_db() -> None:
    cfg = config.MySQLConfig.from_env()
    create_database_if_missing(cfg)
    create_tables(cfg)


if __name__ == "__main__":
    init_db()
