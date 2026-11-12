import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtNum, fmtPct, fmtTs } from "../lib/format";
import type { ExpiryFit, FitCoverage, SeriesSpec } from "../types";

interface Props {
  name: string;
  snapshots: FitCoverage[];               // newest first
  busy: boolean;                          // a fit of this name is queued or running
  version: number;                        // bumps when fits finish, to re-read the open snapshot
  onFitSnapshot: (snapshot: string) => void;
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

const STATUS: Record<string, string> = { ok: "done", failed: "failed" };

export function CoveragePill({ c }: { c: FitCoverage | undefined }) {
  if (!c || c.n_fitted === 0) return <span className="pill queued"><span className="led" />not fitted</span>;
  if (c.n_ok === c.n_expiries) return <span className="pill done"><span className="led" />fitted {c.n_ok}/{c.n_expiries}</span>;
  const failed = c.n_fitted - c.n_ok;
  return <span className="pill warn"><span className="led" />{failed ? `${failed} failed` : "partial"} · {c.n_ok}/{c.n_expiries} ok</span>;
}

/** Under a name's row: its snapshots, and the per-expiry fit of whichever one is open. */
export function FitDetail({ name, snapshots, busy, version, onFitSnapshot, onOpenInPlots }: Props) {
  const [open, setOpen] = useState(snapshots[0]?.snapshot_ts ?? "");
  const [rows, setRows] = useState<ExpiryFit[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setRows(null);
    api.expiryFits(name, open).then(setRows, (e: Error) => setError(e.message));
  }, [name, open, version]);

  return (
    <div className="fit-detail">
      <div className="fit-snaps">
        {snapshots.map((c) => (
          <div key={c.snapshot_ts} className={`fit-snap ${c.snapshot_ts === open ? "active" : ""}`}>
            <button type="button" className="link-btn" aria-pressed={c.snapshot_ts === open} onClick={() => setOpen(c.snapshot_ts)}>
              {fmtTs(c.snapshot_ts).slice(0, 16)}
            </button>
            <CoveragePill c={c} />
            <span className="muted">{c.n_fitted ? `${fmtPct(c.mean_pct_inside, 0)} inside` : ""}</span>
            <button type="button" className="btn-secondary btn-xs" disabled={busy} onClick={() => onFitSnapshot(c.snapshot_ts)}>
              {c.n_fitted ? "Refit" : "Fit"}
            </button>
          </div>
        ))}
      </div>
      {error && <div className="error-text">{error}</div>}
      {open && (rows === null ? <div className="muted empty">Loading…</div> : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Expiry</th><th>T</th><th>Forward</th><th>Fit</th><th>Inside</th><th>RMSE</th><th>Quotes</th>
                <th>Outliers</th><th>σ atm</th><th>Skew</th><th>κ put</th><th>κ call</th><th>Anchor</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.expiry_date}>
                  <td className="name">{r.expiry_date}</td>
                  <td>{fmtNum(r.T, 3)}</td>
                  <td>{fmtNum(r.forward, 2)}</td>
                  <td>{r.fit_status ? <span className={`pill ${STATUS[r.fit_status] ?? "warn"}`}><span className="led" />{r.fit_status}
                    {r.smile_quality_flag === "miss" ? " · miss" : ""}</span> : <span className="muted">not fitted</span>}</td>
                  <td>{fmtPct(r.pct_inside, 0)}</td>
                  <td>{r.smile_fit_rmse == null ? "—" : `${(r.smile_fit_rmse * 100).toFixed(2)} vp`}</td>
                  <td>{r.n_fit_quotes ?? "—"}</td>
                  <td>{r.n_outliers ?? "—"}</td>
                  <td>{fmtPct(r.sigma_atm, 2)}</td>
                  <td>{fmtNum(r.skew, 4)}</td>
                  <td>{fmtNum(r.kappa_put, 4)}</td>
                  <td>{fmtNum(r.kappa_call, 4)}</td>
                  <td className="muted">{r.anchor_snapshot_ts ? fmtTs(r.anchor_snapshot_ts).slice(5, 16) : "—"}</td>
                  <td><button type="button" className="btn-secondary btn-xs"
                    onClick={() => onOpenInPlots({ name, snapshot: open, expiry: r.expiry_date, type: r.fit_status ? "fitted" : "bidask" })}>
                    Plot</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
