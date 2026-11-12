export type XMode = "delta" | "strike" | "moneyness";
export type YMode = "levels" | "diff";
export type SeriesType = "bidask" | "mid" | "fitted";
export type Route = "plots" | "grid" | "lab" | "snapshot" | "schedule" | "fits" | "analysis";

export type ExpiryFilter = "all" | "monthly";

export interface NameOut {
  name_id: number;
  name: string;
  chain_ric: string | null;
  display_name: string | null;
  active: boolean;
  group_name: string | null;
  expiry_filter: ExpiryFilter;
  timezone: string | null;
  last_snapshot_ts: string | null;
}

/** Fields sent when registering a new name. */
export interface NameIn {
  name: string;
  chain_ric: string;
  display_name: string | null;
  group_name: string | null;
  expiry_filter: ExpiryFilter;
  active: boolean;
  timezone: string | null;
}

export type NamePatch = Partial<Omit<NameIn, "name">>;

export interface ChainCandidate { chain_ric: string; title: string; preferred: boolean }

/** What LSEG returned for a typed RIC; nothing is in the database yet. */
export interface NameLookup {
  ric: string;
  found: boolean;
  display_name: string | null;
  spot: number | null;
  currency: string | null;
  vol: number | null;
  candidates: ChainCandidate[];
  error: string | null;
  registered: boolean;
  timezone_guess: string | null;
}

/** A chain's contents after full expansion. */
export interface ChainCheck {
  name: string;
  chain_ric: string;
  n_options: number;
  n_expiries: number;
  first_expiry: string | null;
  last_expiry: string | null;
  strike_min: number | null;
  strike_max: number | null;
  underlying_match: number | null;
  duration_sec: number;
}

export interface MaturityParams {
  forward: number | null;
  discount_factor: number | null;
  n_strikes_forward: number | null;
  n_strikes_df: number | null;
  forward_fit_resid: number | null;
  df_fit_resid: number | null;
  sigma_atm: number | null;
  skew: number | null;
  kappa_call: number | null;
  kappa_put: number | null;
  smile_fit_rmse: number | null;
  smile_quality_flag: string | null;
  fit_status: string | null;
  pct_inside: number | null;
  n_fit_quotes: number | null;
  n_outliers: number | null;
}

type Nullable = (number | null)[];

export interface SmileOut {
  name: string;
  snapshot_ts: string;
  expiry: string;
  T: number | null;
  spot: number | null;
  /** bid-ask fitter's half-spread floor; "inside" checks use it like the fitter does */
  h_min: number;
  params: MaturityParams;
  quotes: {
    strike: number[];
    is_call: boolean[];
    bid: Nullable;
    ask: Nullable;
    bid_iv: Nullable;
    ask_iv: Nullable;
    bid_delta: Nullable;
    ask_delta: Nullable;
    /** forward call-equivalent delta the smile model is evaluated at */
    fwd_delta: Nullable;
  };
}

export interface JobOut {
  id: number;
  kind: "snapshot" | "lookup" | "check" | "fit";
  name: string;
  status: "queued" | "running" | "done" | "failed";
  submitted_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  origin: "manual" | "schedule";
  snapshot_ts: string | null;
  spot: number | null;
  window_vol: number | null;
  window_size: number | null;
  n_quotes: number | null;
  n_maturities: number | null;
  duration_sec: number | null;
  lookup: NameLookup[] | null;
  check: ChainCheck | null;
  fit: FitSnapshotSummary[] | null;
}

/** One line on the Plots chart: which smile, drawn how. */
export interface SeriesSpec {
  id: number;
  name: string;
  snapshot: string;
  expiry: string;
  type: SeriesType;
  baseline: boolean;
}

export type Day = "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat" | "Sun";
export const DAYS: Day[] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export interface ScheduleRun {
  name: string;
  scheduled_for_utc: string;
  local_label: string | null;
  status: "queued" | "skipped_busy" | "missed" | "done" | "failed";
  job_id: number | null;
  reason: string | null;
}

/** One name's schedule; times are "HH:MM" local to `timezone`. All *_utc strings are naive UTC. */
export interface ScheduleRow {
  name: string;
  display_name: string | null;
  group_name: string | null;
  active: boolean;
  timezone: string | null;
  enabled: boolean;
  days: Day[];
  times: string[];
  next_fire_utc: string | null;
  next_fire_label: string | null;
  last_run: ScheduleRun | null;
  est_duration_sec: number | null;
}

export interface ScheduleOut { paused: boolean; names: ScheduleRow[] }

export interface ScheduleItemIn { name: string; times: string[]; days: Day[]; enabled: boolean }

export interface SchedulerStatus {
  enabled: boolean;
  paused: boolean;
  last_tick_utc: string | null;
  upcoming: { name: string; fire_utc: string; local_label: string }[];
  recent_runs: ScheduleRun[];
}

export type FitMode = "latest" | "unfitted" | "snapshot";

/** One snapshot of one name: how many expiries are fitted and how well. */
export interface FitCoverage {
  name: string;
  snapshot_ts: string;
  n_expiries: number;
  n_fitted: number;
  n_ok: number;
  mean_pct_inside: number | null;
  min_pct_inside: number | null;
  n_outliers: number | null;
  last_fit_ts: string | null;
}

export interface ExpiryFit {
  expiry_date: string;
  T: number | null;
  forward: number | null;
  fit_status: string | null;
  smile_quality_flag: string | null;
  pct_inside: number | null;
  smile_fit_rmse: number | null;
  n_fit_quotes: number | null;
  n_outliers: number | null;
  sigma_atm: number | null;
  skew: number | null;
  kappa_put: number | null;
  kappa_call: number | null;
  refit: boolean | null;
  anchor_snapshot_ts: string | null;
  fit_ts: string | null;
}

export interface FitSnapshotSummary {
  snapshot_ts: string;
  n_expiries: number;
  n_ok: number;
  mean_pct_inside: number | null;
  min_pct_inside: number | null;
  n_outliers: number;
  n_model_miss: number;
  duration_sec: number;
}
