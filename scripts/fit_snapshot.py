"""Fit the per-expiry delta smile for stored snapshots and persist the results.

Usage:
    python scripts/fit_snapshot.py --underlying .STOXX50E                  # latest snapshot
    python scripts/fit_snapshot.py --underlying .STOXX50E --snapshot-ts "2026-11-06 12:38:55"
    python scripts/fit_snapshot.py --underlying .STOXX50E --all-unfitted   # oldest first, chaining anchors
    python scripts/fit_snapshot.py --underlying .STOXX50E --no-anchor

Needs the fit columns in MySQL: run `python -m vol_fitter.db.init_db` once
after pulling (it adds missing columns/tables, never drops anything).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vol_fitter.db.engine import build_engine
from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.orchestration.fit_run import run_fit, run_unfitted
from vol_fitter.orchestration.models import FitRunResult


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--underlying", default=".STOXX50E")
    parser.add_argument("--snapshot-ts", default=None, help="default: latest stored snapshot")
    parser.add_argument("--all-unfitted", action="store_true")
    parser.add_argument("--no-anchor", action="store_true", help="ignore previous fits (no warm start/anchor)")
    return parser.parse_args()


def _print(result: FitRunResult) -> None:
    print(f"\n{result.name} @ {result.snapshot_ts}  ({result.n_quotes} quotes, {result.duration_sec:.1f}s)")
    print(f"{'expiry':<12}{'status':<8}{'inside':>8}{'n':>5}{'out':>5}{'miss':>5}"
          f"{'atm':>8}{'skew':>8}{'k_put':>8}{'k_call':>8}  anchor")
    for s in result.expiries:
        a = s.anchor_snapshot_ts.strftime("%m-%d %H:%M") if s.anchor_snapshot_ts else "-"
        print(f"{s.expiry_date!s:<12}{s.status:<8}{s.pct_inside:>8.1%}{s.n_quotes:>5}{s.n_outliers:>5}"
              f"{s.n_model_miss:>5}" + "".join(f"{v:>8.4f}" for v in s.params) + f"  {a}")


if __name__ == "__main__":
    args = _parse_args()
    repo = VolFitterRepository(build_engine())
    anchor = not args.no_anchor
    if args.all_unfitted:
        results = run_unfitted(repo, args.underlying, anchor=anchor)
    else:
        ts = pd.Timestamp(args.snapshot_ts).to_pydatetime() if args.snapshot_ts else None
        results = [run_fit(repo, args.underlying, ts, anchor=anchor)]
    for r in results:
        _print(r)
    if not results:
        print("nothing to fit")
