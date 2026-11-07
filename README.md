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
| `vol_fitter.orchestration` | `run_snapshot()`: snap → price → persist one underlying. Shared by the CLI and the web console. |
| `vol_fitter.web` | FastAPI app: REST API under `/api` plus the built frontend, on one port. |

Actual vol-surface fitting (the per-expiry delta-space smile) is a later
phase, built on top of these.

## Scripts

| File | What it does |
|---|---|
| `scripts/batch_probe.py` | Finds the largest `get_data` batch that works for a chain. Run once per chain. |
| `scripts/snap_and_price.py` | Snaps a live chain, prices it (forwards, implied vol, Greeks), persists everything to MySQL. |

```
python scripts/snap_and_price.py --underlying .STOXX50E
```

Pass `--chain-ric` the first time you use a new underlying; after that it's
looked up from the `names` table.

## Web console

React + Plotly frontend in `frontend/`, served by FastAPI. Pages: Plots
(smiles vs 1 − call Δ, strike or moneyness; overlay and diff series),
Grid (all expiries of one snapshot, or one expiry across names), Snapshot
(run snapshots, watch progress). Fits and Analysis are placeholders until
fitting exists.

Because the repo lives on Google Drive (which can't hold `node_modules`),
npm/TypeScript/Vite run from a local toolchain under `~\.vol_fitter\` via
`frontend/toolchain.py`; only the small `frontend/dist/` build lands in the
repo. Node.js must be installed.

```
python frontend/toolchain.py build                  # one-off; re-run after frontend changes
uvicorn vol_fitter.web.app:app --port 8000          # then open http://localhost:8000
```

For frontend work with hot reload, run the uvicorn command above plus
`python frontend/toolchain.py dev` and open http://localhost:5173 (Vite
proxies `/api` to :8000).

Everything is one process on one port, so exposing it later is
`cloudflared tunnel --url http://localhost:8000`. There's no
authentication yet — add some before putting it on a public tunnel.

## Tests

```
pytest
```

Pricing-library tests (`robust_regression`, `forward_fitter`,
`black76_pricer`) use synthetic data only. `test_repository.py` and
`test_web_api.py` run against a disposable local `<db>_test` MySQL database
(the web tests use a fake snapshot runner, never LSEG) and are skipped
automatically if MySQL isn't reachable.
