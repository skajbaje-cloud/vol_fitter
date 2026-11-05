# vol_fitter

Delta-space implied vol surface fitter, fed by LSEG Workspace chain
snapshots, persisted to MySQL. Three foundation libraries (snapshot,
pricing, database) come before any smile/surface fitting — see
`src/vol_fitter/`.

## Setup (Anaconda Prompt)

```
conda create -n vol_fitter python=3.12 -y
conda activate vol_fitter
cd /d "G:\My Drive\SK work\Trading\Vol Fitter\vol_fitter"
pip install -e .
copy .env.example .env   REM then fill in your local MySQL credentials
python -m vol_fitter.db.init_db   REM creates the database + tables
```

LSEG Workspace must be running and signed in for anything that snaps live
quotes.

## Layout

| Package | What it does |
|---|---|
| `vol_fitter.snapshot` | Point-in-time option chain snapshots from LSEG (universe cache, std-dev window, batching/retries). |
| `vol_fitter.pricing` | Per-maturity forward/discount-factor (robust LAD regression on put-call parity) and Black-76 price/implied-vol/Greeks (vectorized, Jäckel-style OTM reduction for the IV solve). |
| `vol_fitter.db` | MySQL schema (`names`, `snapshots`, `raw_quotes`, `maturity_params`, `master_params`) and a thin SQLAlchemy Core repository. |

Actual vol-surface fitting (the per-expiry delta-space smile) is a later
phase, built on top of these three.

## Scripts

| File | What it does |
|---|---|
| `scripts/batch_probe.py` | Finds the largest `get_data` batch that works for a chain. Run once per chain. |
| `scripts/snap_and_price.py` | Snaps a live chain, prices it (forwards, implied vol, Greeks), persists everything to MySQL. |

```
python scripts/snap_and_price.py --underlying .STOXX50E --chain-ric "0#STXE*.EX" --vol-ric .V6I3
```

## Tests

```
pytest
```

Pricing-library tests (`robust_regression`, `forward_fitter`,
`black76_pricer`) use synthetic data only. `test_repository.py` runs
against a local `<db>_test` MySQL database and is skipped automatically if
MySQL isn't reachable.
