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
# Universe CSV cache: the repo folder (on Google Drive). Drive sync can briefly lock a file;
# UniverseCache then rebuilds from LSEG instead of failing the snapshot.
UNIVERSE_CACHE_DIR = Path(os.environ.get("VOL_FITTER_CACHE_DIR", _REPO_ROOT))
CALL_SD_WINDOW = (-1.0, 4.0)           # std-dev window around spot, calls
PUT_SD_WINDOW = (-4.0, 1.0)            # std-dev window around spot, puts

# 40-day realized vol, requestable directly on any underlying RIC (equity,
# ETF, or index) -- used only to size the std-dev window, not for pricing.
VOL_FIELD = "TR.Volatility40D"

# ---- snapshot schedule ----
# The scheduler thread runs inside the web server (uvicorn); VOL_FITTER_SCHEDULER=off disables it.
SCHEDULER_ENABLED = os.environ.get("VOL_FITTER_SCHEDULER", "on").lower() not in ("0", "off", "false", "no")
SCHEDULE_TICK_SEC = 20                 # how often due firings are checked
SCHEDULE_GRACE_MIN = 15                # a firing later than this (server was down) is recorded as missed, not run late
SCHEDULE_MAX_SLOTS = 5                 # snap times per name per day
SCHEDULE_MIN_GAP_MIN = 10              # UI warns when a name's times are closer than this
SCHEDULE_MISSED_LOOKBACK_DAYS = 3      # how far back missed firings are recorded after downtime

# ---- pricing hyperparameters ----
# Strike-selection band for the forward (F) LAD regression stage, in
# abs(log-moneyness) = |ln(K/F_guess)|. None = use every strike available.
# Narrow on purpose: wings add noise without adding information about F.
FORWARD_MONEYNESS_BAND: float | None = 0.05

# DF regression deliberately uses the full strike range (wings included) —
# no band here.

# ---- smile model (per-expiry, delta space) ----
# sigma(z) = atm + skew*z + kappa_put*(z+)^2 + kappa_call*(z-)^2,  z = Phi^-1(forward call delta)
# kappa = vol added above the skew line at z = +/-1 (about the 16-delta put / call).
#                    sigma_atm  skew  kappa_put  kappa_call
SMILE_LOWER = (0.01, -1.0, -0.5, -0.5)
SMILE_UPPER = (3.00, 1.0, 1.0, 1.0)
SMILE_VOL_FLOOR = 0.01                 # model vol kept above this across the whole delta range

# ---- bid-ask fit: previous-fit anchor (parameter space) ----
# 0 disables anchoring. Placeholders until calibrated from day-to-day parameter moves.
ANCHOR_LAMBDA = 0.0
ANCHOR_SCALE = (0.01, 0.01, 0.01, 0.01)  # per-parameter "1 unit of move", same order as SMILE_LOWER
ANCHOR_MAX_AGE_DAYS = 5

IV_SOLVER_MIN_TOTAL_STDEV = 1e-7      # bisection bracket lower bound on sigma*sqrt(T)
IV_SOLVER_MAX_TOTAL_STDEV = 10.0       # bisection bracket upper bound on sigma*sqrt(T), expanded if needed
IV_SOLVER_BISECTION_ITERS = 40
IV_SOLVER_HALLEY_ITERS = 4
