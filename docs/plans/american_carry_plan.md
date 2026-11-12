# American options: dividend curves, repo and market-implied carry calibration

## Context

ETF and single-stock options are American, but the pricer assumes European options throughout:
- the forward and discount factor come from a put-call parity fit;
- implied vols use Black-76.

On the 2026-11-08 ETF snapshots the fitted discount factors are 0.44–1.54. Every IV, delta and smile fit for those names is unreliable.

Target design:
- Dividends are **discrete**: LSEG ex-dates plus LSEG amounts and consensus estimates, stored raw and only when they change.
- Discounting uses a **SOFR curve**. Financing uses the **SPX repo curve** (from TRFs), both entered by you to begin with.
- Per name and snapshot, an **optimizer** adjusts dividend amounts, unannounced ex-dates and one repo spread so that put and call IVs line up across all maturities, outliers excluded.
- American IVs then come from a Leisen-Reimer tree using that calibrated curve.
- The smile model and fitter stay unchanged.

**Settled decisions**

| Topic | Choice |
|---|---|
| Discount curve | SOFR curve, entered |
| SPX repo | Entered as a spread over SOFR by tenor |
| Repo per name | One flat spread `s` over SPX repo, with its prior centred on 0 |
| Announced dividends | Held fixed (amount and date) |
| Where calibration runs | A separate CPU pricing worker; the LSEG queue never waits on it |
| Indices (European) | Keep today's parity fit, untouched |

## Model conventions

| Quantity | Definition |
|---|---|
| Discounting | `DF(T) = exp(−r(T)·T)`, with r = SOFR zero rate, continuously compounded, ACT/365 |
| Name financing rate | `b(T) = r(T) + spread_SPX(T) + s` |
| Growth factor | `G(t) = exp(b(t)·t)` |
| Forward | `F(T) = G(T)·(S − Σ_{t_i ≤ T} D_i / G(t_i))` |
| Time | T stays calendar time, as now; business-day T is still deferred |

## Phase 1: inputs (raw dividends, rates, exercise style)

No change to pricing in this phase.

**Schema** (`db/schema.py`, added via `init_db`)
- `names.exercise_style`: `european` | `american`.
  - Set automatically at look-up: a RIC starting with "." is european, anything else american.
  - Existing rows are backfilled by the same rule. Editable in the row editor.
- Dividend events, one version per change:
  - `div_event_versions`: version_id, name_id, fetched_ts, window_start, content_hash.
  - `div_events`: version_id, ex_date, div_type, amount (nullable), pay_date, announce_date, currency.
- Consensus estimates, versioned separately because they revise more often than events:
  - `dps_versions`: version_id, name_id, fetched_ts, content_hash.
  - `dps_estimates`: version_id, period (FQ1..FQ5, FY1..FY3), period_end, dps_mean, n_estimates.
- Rate curves:
  - `rate_curve_versions`: version_id, curve (`USD_SOFR` | `SPX_REPO_SPREAD`), as_of, source (`manual`), entered_ts, note.
  - `rate_curve_points`: version_id, tenor_days, value. SOFR values are zero rates; the repo spread is in decimal.
- `snapshots` gains:
  - `div_event_version_id`, `dps_version_id`, `sofr_version_id`, `repo_version_id`: what priced it.
  - `pricing_status`: raw | priced | failed.

**Fetching:** `carry/lseg_dividends.py` → `DividendFetcher(client).fetch(rics)`.
- Events:
  - Fields `TR.DivExDate`, `TR.DivUnadjustedGross`, `TR.DivPayDate`, `TR.DivAnnouncementDate`, `TR.DivType`, `TR.DivCurr`.
  - Window `SDate=-400D, EDate=+3Y`, with **`DateType=ED`**. Without it the window filters on the announcement date and misses upcoming dividends; this was confirmed in testing.
- Estimates: `TR.DPSMean(Period=FQ1..FQ5, FY1..FY3)` plus `.periodenddate` and `TR.DPSNumOfEst`.
- Runs inside the snapshot job for american names only, on the LSEG session the job already holds. Cost is about 1s.

**Change detection:** `db/carry_queries.py` (`CarryQueriesMixin`).
- Compare the new fetch with the latest version over the overlapping window only: ex_date ≥ the new window_start. Amounts are rounded to 1e-6.
- A new version is written only if something differs. Events sliding out of the trailing window are not a change.
- Changes that do count:
  - an ETF amount getting filled in;
  - a new announcement;
  - a cancelled event;
  - a consensus revision.

**Rates entry**
- `scripts/set_rates.py --curve USD_SOFR --as-of 2026-11-06 1M=4.31 3M=4.28 …` (percent input).
- `POST /api/rates` and `GET /api/rates`.
- At pricing time, a snapshot uses the latest version with as_of ≤ snapshot date. It logs a warning if that version is older than `RATES_MAX_AGE_DAYS`.
- Interpolation: linear in zero rate and flat beyond the ends (`carry/curves.py`, `RateCurve`).

## Phase 2: American pricing with the prior curve

This alone fixes the broken DFs, before any optimizer.

**Prior curve:** `carry/prior.py` → `DivPriorBuilder.build(events, dps, spot_date, horizon)` → list of `DivPoint(ex_date, amount, kind, fixed, sigma_rel)`.
- `announced`: future ex-date with a known amount. Fixed.
- `scheduled`: future ex-date with a blank amount (ETFs). The amount comes from the event closest to 1 year earlier, so seasonality is kept. Starting σ_rel 15%.
- `projected`: dates beyond the last LSEG event.
  - Frequency is inferred from the trailing-year count (12, 4, 2 or 1 a year). Dates are the last ex-date plus k periods, moved to a business day.
  - Stock amounts come from the FQ consensus whose fiscal quarter contains the ex-date. Past FQ5, use FY2 or FY3 divided by the frequency.
  - ETF amounts use the same quarter last year.
  - Starting σ_rel 10–30%, growing with horizon.
- Excluded:
  - `Extra`/special types with no amount, such as the SPY 12-31 placeholder;
  - currency mismatches (logged).
- Horizon is the last listed expiry plus one period.

**Tree:** `pricing/american_tree.py` → `LeisenReimerTree(n_steps)`.
- Escrowed-dividend model: S* = S − PV_b(divs within the option's life) follows GBM with drift b, and each step discounts at r.
- Node stock price = S* + PV of the remaining dividends. That price is used for the exercise test.
- Odd step count. Ex-dates snap to the nearest step; a minimum steps-per-year setting keeps short expiries accurate.
- Vectorized in numpy across all options of one expiry (array of n options by N+1 nodes).
- numba isn't installed. It would only be added, with your OK, if the benchmarks below miss target.

**American IV:** `pricing/american_iv.py` → `AmericanIVSolver`.
- Vectorized bracketed Newton/secant on σ, with vega from a tree bump.
- NaN when the price is at or below the exercise value, which matches the Black-76 behaviour today.

**Pricer:** `pricing/american_pricer.py` → `AmericanPricer.price_quotes(quotes, carry)`.
- Returns the same columns as `Black76Pricer.price_quotes`, so `FitFrameBuilder` and the smile fit work unchanged:
  - bid_iv and ask_iv are American-implied;
  - Greeks are Black-76 at the American IV, using the model F and SOFR DF.
- Adds `raw_quotes.early_ex_premium`: the tree price minus the European price at the same σ, at mid.
- `maturity_params`:
  - forward = model F, discount_factor = SOFR DF;
  - new columns `repo_rate`, `pv_divs`, `pricing_model` (`black76` | `american_lr`).

**Pricing worker:** `web/jobs.py`.
- `JobQueue` gets a name and its own kinds. The app runs two queues:
  - `lseg`: snapshot, lookup, check;
  - `cpu`: price, reprice.
- `/api/jobs` lists both.
- `run_snapshot` (`orchestration/snapshot_run.py`):
  - **european** names: unchanged.
  - **american** names:
    1. Store the raw bid/ask quotes, with IVs left NULL.
    2. Set `pricing_status='raw'`.
    3. Return the result together with a "price this" handoff, which the app submits to the cpu queue.
- `orchestration/price_run.py` → `run_price(repo, name, snapshot_ts)`:
  1. Load the raw quotes, the dividend and rate versions, and the prior.
  2. Calibrate (Phase 3; before that exists, the prior is used as is).
  3. Price, persist, and set `priced`.
- Smile fits only run on priced snapshots.

## Phase 3: carry calibrator

Package `carry/`: `pairs.py`, `residuals.py`, `calibrator.py`, `date_search.py`. Data classes go in `carry/models.py`.

**Pairs** (`PairBuilder`)
- Call and put at the same expiry and strike, both with a valid quote.
- Restricted to the OTM leg's |forward delta| between 0.05 and 0.50, so the ITM leg sits roughly between 0.50 and 0.95.
- Thinned to at most about 40 per expiry, keeping them nearest ATM.

**What "lined up" means:** the bid-ask IV intervals of the call and the put overlap. This is evaluated stably, without inverting deep-ITM prices:
1. Solve σ_bid and σ_ask from the **OTM** leg.
2. Price the **ITM** leg at both vols with the tree.
3. Gap = max(0, P_itm(σ_bid) − ask_itm, bid_itm − P_itm(σ_ask)), divided by the ITM half-spread.
4. Residual = `ExpWallPenalty`-shaped wall on the gap (reused from `bidask_fit/penalty.py`), plus a weak mid tiebreak: (P_itm(σ_mid) − mid_itm) / h_itm.
5. Weight 1/n_pairs per expiry, so every maturity counts equally.

**Parameters**
- Amounts of the non-fixed dividends with ex_date ≤ the last expiry. Bounds are ≥ 0.
- The repo spread `s`.
- Unannounced ex-dates are handled separately (see "Dates" below).

**Penalties** (stacked residuals)
- Prior: (D_i − D_i⁰) / (σ_rel,i·D_i⁰).
- Repo: s / σ_s, with `CARRY_REPO_SIGMA` set in config.
- Smoothness between consecutive regular dividends. For ETFs this is measured against last year's seasonal pattern rather than flat.
- Optional anchor to the previous snapshot's calibrated curve, weighted by `CARRY_ANCHOR_LAMBDA`, default 0 (like the smile anchor).
- A dividend sitting alone between two expiries is only identified through the forward, so its prior keeps it sensible. Repo and dividends are told apart only by timing, which is why `s` gets a firm prior.

**Solve** (staged for speed)
1. **Forward stage.** Per expiry, solve for F from near-ATM parity on European-equivalent prices, then fit the amounts and `s` to the forward term structure using the closed-form F(T). Repeat 2–3 times. No tree is involved inside the optimizer, so this takes milliseconds.
2. **Full stage.** `scipy.optimize.least_squares` (trf, soft_l1 loss) on the pair objective, warm-started from stage 1.
   - Finite-difference Jacobian with `jac_sparsity`: dividend i only affects expiries after t_i.
   - Fewer tree steps here (about 101) than in the final pricing (about 201).
3. **Outliers.** Classify pair gaps with `OutlierClassifier` (`bidask_fit/outliers.py`), feeding the gap as v_ask/v_bid along a moneyness axis. Exclude outliers and refit once, with the guard rails as in the smile fitter.
4. **Dates** (`DateProfiler`). Only for non-announced ex-dates where a ±5 business-day window crosses an expiry. Try each candidate side greedily, re-solve warm-started, and keep the lower objective plus date-prior penalty. Capped at a few candidates per name.
5. **Final pricing.** Run `AmericanPricer` on all quotes with the calibrated curve.

**Outputs** (`CarryQueriesMixin`)
- `carry_fits`, one row per (name_id, snapshot_ts):
  - repo_spread, status, objective, n_pairs, n_outliers, pct_pairs_overlap;
  - n_iter, duration;
  - the four input version ids, fit_ts;
  - flags: spread at bound, dividend moved more than X% from its prior, dates changed.
- `carry_fit_divs`: ex_date, amount, prior_amount, prior_ex_date, kind, fixed.
- `carry_fit_pairs`: expiry, strike, gap, tiebreak, classification, excluded. These are the diagnostics for the UI.

**Performance targets** (benchmarked in tests): calibration ≤ 60 s per name, final pricing ≤ 15 s per name.

## Phase 4: repricing and console

- `reprice` cpu job, plus `scripts/reprice.py --underlying XLB.P [--snapshot-ts]`. Runs `run_price` on stored snapshots from their saved bid/ask; no LSEG needed.
  - Snapshots taken before Phase 1 have no dividend version. They use the earliest version stored, and their fit is flagged.
- Console additions:
  - Exercise style in the `NameEditor` row editor, using the existing Seg control.
  - A pricing-status pill in `NamesTable` / `JobTable`.
  - A carry view:
    - prior vs implied dividends against ex-date;
    - repo spread;
    - put vs call IVs per expiry, with excluded pairs marked.
  - A rates form, which can follow later; the CLI covers rates entry first.

## Tests

| File | Covers |
|---|---|
| `test_american_tree.py` | • American call with no dividends equals Black-Scholes<br>• American put matches published binomial or Leisen-Reimer reference values<br>• Prices converge as steps increase<br>• Discrete dividend vs the escrowed closed form for European options<br>• Call early exercise just before an ex-date |
| `test_american_iv.py` | • Price → vol → price round trip across moneyness and maturity<br>• NaN below exercise value |
| `test_div_prior.py` | • AAPL-like announced dividend plus consensus mapping<br>• ETF scheduled dates with blank amounts filled seasonally<br>• SPY extra placeholder dropped<br>• Frequency inference |
| `test_carry_storage.py` | • Same fetch gives no new version<br>• Sliding window gives no new version<br>• Amount filled in gives a new version<br>• Rates as-of lookup and interpolation |
| `test_carry_calibrator.py` | • Synthetic quotes from known dividends and repo, plus noise and planted outliers: recovers amounts and `s` within tolerance and excludes the outliers<br>• Two dividends in one expiry interval stay near the prior split<br>• Announced dividends untouched |
| `test_web_api.py` | • Rates routes<br>• The cpu queue's price job<br>• Exercise style patch |

## Verification

1. `pytest`: all existing tests plus the new ones, with the tree and IV benchmarks printing timings.
2. `init_db` migration on the live database; check the new tables and columns in Workbench.
3. You enter the SOFR and SPX repo-spread curves with `set_rates.py`.
4. Snapshot XLB.P and AAPL.O from the console:
   - dividend versions get stored;
   - a second snapshot creates no new version;
   - the price job runs on the cpu queue while the LSEG queue stays free.
5. Compare put/call alignment, old against new: Black-76 with free DF vs American with the calibrated curve. Check:
   - pct of pairs overlapping per expiry;
   - implied dividends vs prior;
   - `s`.
6. Reprice the 11-08 ETF snapshots and run the smile fit. Check that the Plots tab shows sane smiles for the ETFs.

## Order of work

Phase 1, then 2, then 3, then 4. Each phase ends green and usable:
- After Phase 2, ETFs price on the prior curve.
- After Phase 3, ETFs price on the market-implied curve.

Files stay under 200 lines, with data classes in `models.py` files and a logger in every module.
