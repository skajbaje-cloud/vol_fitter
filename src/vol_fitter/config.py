"""Central configuration: env/credentials loading and tunable hyperparameters.

Every other module reads knobs from here rather than hardcoding constants,
so behavior can be changed in one place.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str

    @classmethod
    def from_env(cls) -> "MySQLConfig":
        return cls(
            host=os.environ.get("VOL_FITTER_MYSQL_HOST", "localhost"),
            port=int(os.environ.get("VOL_FITTER_MYSQL_PORT", "3306")),
            user=os.environ.get("VOL_FITTER_MYSQL_USER", ""),
            password=os.environ.get("VOL_FITTER_MYSQL_PASSWORD", ""),
            database=os.environ.get("VOL_FITTER_MYSQL_DB", "vol_fitter"),
        )


LOG_LEVEL = os.environ.get("VOL_FITTER_LOG_LEVEL", "INFO")

# ---- web ----
_REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = Path(os.environ.get("VOL_FITTER_FRONTEND_DIST", _REPO_ROOT / "frontend" / "dist"))

# ---- snapshot hyperparameters ----
MAX_SNAP = 4000                       # largest safe get_data batch (see scripts/batch_probe.py)
UNIVERSE_MAX_AGE_DAYS = 7
CALL_SD_WINDOW = (-1.0, 4.0)           # std-dev window around spot, calls
PUT_SD_WINDOW = (-4.0, 1.0)            # std-dev window around spot, puts

# 40-day realized vol, requestable directly on any underlying RIC (equity,
# ETF, or index) -- used only to size the std-dev window, not for pricing.
VOL_FIELD = "TR.Volatility40D"

# ---- pricing hyperparameters ----
# Strike-selection band for the forward (F) LAD regression stage, in
# abs(log-moneyness) = |ln(K/F_guess)|. None = use every strike available.
# Narrow on purpose: wings add noise without adding information about F.
FORWARD_MONEYNESS_BAND: float | None = 0.05

# DF regression deliberately uses the full strike range (wings included) —
# no band here.

IV_SOLVER_MIN_TOTAL_STDEV = 1e-7       # bisection bracket lower bound on sigma*sqrt(T)
IV_SOLVER_MAX_TOTAL_STDEV = 10.0       # bisection bracket upper bound on sigma*sqrt(T), expanded if needed
IV_SOLVER_BISECTION_ITERS = 40
IV_SOLVER_HALLEY_ITERS = 4
