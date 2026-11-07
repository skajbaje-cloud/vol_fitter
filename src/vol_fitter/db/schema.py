"""SQLAlchemy Core table definitions for the vol_fitter MySQL database.

Pure schema (data shape), no connection/session logic here — see engine.py
and repository.py for that.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData()

# MySQL has no native DOUBLE-precision float distinct from FLOAT via the
# generic SQLAlchemy type in all dialects, so use Float(53) uniformly for
# "double precision" columns.
DOUBLE = Float(53)

names = Table(
    "names",
    metadata,
    Column("name_id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(32), unique=True, nullable=False),
    Column("chain_ric", String(64)),
    Column("display_name", String(128)),
    Column("active", Boolean, default=True),
    Column("created_ts", DateTime),
)

snapshots = Table(
    "snapshots",
    metadata,
    Column("name_id", Integer, ForeignKey("names.name_id"), nullable=False),
    Column("snapshot_ts", DateTime, nullable=False),
    Column("spot", DOUBLE),
    Column("universe_size", Integer),
    Column("window_size", Integer),
    Column("snap_duration_sec", DOUBLE),
    Column("status", String(16)),
    UniqueConstraint("name_id", "snapshot_ts", name="uq_snapshots_name_ts"),
)

raw_quotes = Table(
    "raw_quotes",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("name_id", Integer, ForeignKey("names.name_id"), nullable=False),
    Column("snapshot_ts", DateTime, nullable=False),
    Column("instrument", String(32), nullable=False),
    Column("strike", DOUBLE),
    Column("expiry_date", Date),
    Column("T", DOUBLE),
    Column("is_call", Boolean),
    Column("bid", DOUBLE),
    Column("ask", DOUBLE),
    Column("bid_iv", DOUBLE),
    Column("ask_iv", DOUBLE),
    Column("bid_delta", DOUBLE),
    Column("ask_delta", DOUBLE),
    Column("bid_gamma", DOUBLE),
    Column("ask_gamma", DOUBLE),
    Column("bid_vega", DOUBLE),
    Column("ask_vega", DOUBLE),
    Column("bid_theta", DOUBLE),
    Column("ask_theta", DOUBLE),
    Column("bid_rho", DOUBLE),
    Column("ask_rho", DOUBLE),
    UniqueConstraint("name_id", "snapshot_ts", "instrument", name="uq_raw_quotes_name_ts_instrument"),
)

maturity_params = Table(
    "maturity_params",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("name_id", Integer, ForeignKey("names.name_id"), nullable=False),
    Column("snapshot_ts", DateTime, nullable=False),
    Column("expiry_date", Date, nullable=False),
    Column("T", DOUBLE),
    Column("forward", DOUBLE),
    Column("discount_factor", DOUBLE),
    Column("n_strikes_forward", Integer),
    Column("n_strikes_df", Integer),
    Column("forward_fit_resid", DOUBLE),
    Column("df_fit_resid", DOUBLE),
    # Phase 2 (per-expiry smile fit) columns: nullable, unpopulated for now.
    Column("sigma_atm", DOUBLE),
    Column("skew", DOUBLE),
    Column("kappa_call", DOUBLE),
    Column("kappa_put", DOUBLE),
    Column("smile_fit_rmse", DOUBLE),
    Column("smile_quality_flag", String(8)),
    UniqueConstraint("name_id", "snapshot_ts", "expiry_date", name="uq_maturity_params_name_ts_expiry"),
)

master_params = Table(
    "master_params",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("name_id", Integer, ForeignKey("names.name_id"), nullable=False),
    Column("snapshot_ts", DateTime, nullable=False),
    # Phase 2/3 (name-level master surface) columns: nullable, unpopulated for now.
    Column("vol_level", DOUBLE),
    Column("term_structure", DOUBLE),
    Column("skew_level", DOUBLE),
    Column("kappa_call_level", DOUBLE),
    Column("kappa_put_level", DOUBLE),
    Column("fit_rmse", DOUBLE),
    UniqueConstraint("name_id", "snapshot_ts", name="uq_master_params_name_ts"),
)
