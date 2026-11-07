export type XMode = "delta" | "strike" | "moneyness";
export type YMode = "levels" | "diff";
export type SeriesType = "bidask" | "mid" | "fitted";
export type Route = "plots" | "grid" | "snapshot" | "fits" | "analysis";

export interface NameOut {
  name_id: number;
  name: string;
  chain_ric: string | null;
  display_name: string | null;
  active: boolean;
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
}

type Nullable = (number | null)[];

export interface SmileOut {
  name: string;
  snapshot_ts: string;
  expiry: string;
  T: number | null;
  spot: number | null;
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
  };
}

export interface JobOut {
  id: number;
  kind: string;
  name: string;
  status: "queued" | "running" | "done" | "failed";
  submitted_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  snapshot_ts: string | null;
  spot: number | null;
  window_vol: number | null;
  window_size: number | null;
  n_quotes: number | null;
  n_maturities: number | null;
  duration_sec: number | null;
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
