import { Fragment, useEffect, useRef } from "react";
import { fmtPct, fmtTs } from "../lib/format";
import type { FitCoverage, JobOut, SeriesSpec } from "../types";
import { CoveragePill, FitDetail } from "./FitDetail";

interface Props {
  names: string[];
  coverage: Map<string, FitCoverage[]>;   // name -> its snapshots, newest first
  selected: Set<string>;
  expanded: string | null;
  lastJob: (name: string) => JobOut | undefined;
  version: number;
  onToggle: (name: string) => void;
  onToggleAll: () => void;
  onExpand: (name: string | null) => void;
  onFitSnapshot: (name: string, snapshot: string) => void;
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

const COLS = 11;
const JOB_PILL = { queued: "queued", running: "fitting", done: "fitted", failed: "failed" } as const;
const live = (j?: JobOut) => !!j && (j.status === "queued" || j.status === "running");

export function FitsTable(p: Props) {
  const all = useRef<HTMLInputElement>(null);
  const n = p.names.filter((x) => p.selected.has(x)).length;
  useEffect(() => { if (all.current) all.current.indeterminate = n > 0 && n < p.names.length; }, [n, p.names.length]);

  return (
    <div className="table-scroll">
      <table className="data-table names-table">
        <thead>
          <tr>
            <th className="sel"><input ref={all} type="checkbox" aria-label="Select all names"
              checked={p.names.length > 0 && n === p.names.length} onChange={p.onToggleAll} /></th>
            <th>Name</th><th>Latest snapshot</th><th>Latest fit</th><th>Mean inside</th><th>Worst expiry</th>
            <th>Outliers</th><th>Unfitted snaps</th><th>Last fitted</th><th>Job</th><th />
          </tr>
        </thead>
        <tbody>
          {p.names.map((name) => {
            const snaps = p.coverage.get(name) ?? [];
            const latest = snaps[0];
            const unfitted = snaps.filter((c) => c.n_fitted === 0).length;
            const job = p.lastJob(name);
            const open = p.expanded === name;
            return (
              <Fragment key={name}>
                <tr className={open ? "open" : ""}>
                  <td className="sel"><input type="checkbox" aria-label={`Select ${name}`} checked={p.selected.has(name)} onChange={() => p.onToggle(name)} /></td>
                  <td className="name">{name}</td>
                  <td>{latest ? fmtTs(latest.snapshot_ts).slice(5, 16) : "—"}</td>
                  <td><CoveragePill c={latest} /></td>
                  <td>{fmtPct(latest?.mean_pct_inside, 0)}</td>
                  <td>{fmtPct(latest?.min_pct_inside, 0)}</td>
                  <td>{latest?.n_outliers ?? "—"}</td>
                  <td>{unfitted ? `${unfitted} of ${snaps.length}` : <span className="muted">none</span>}</td>
                  <td>{latest?.last_fit_ts ? fmtTs(latest.last_fit_ts).slice(5, 16) : "—"}</td>
                  <td>{job ? <span className={`pill ${job.status}`} title={job.error ?? ""}><span className="led" />{JOB_PILL[job.status]}</span>
                    : <span className="muted">—</span>}</td>
                  <td><button type="button" className="icon-btn edit-btn" aria-expanded={open} aria-label={`Details for ${name}`}
                    onClick={() => p.onExpand(open ? null : name)}>{open ? "▴" : "▾"}</button></td>
                </tr>
                {open && (
                  <tr className="editor-row"><td colSpan={COLS}>
                    <FitDetail name={name} snapshots={snaps} busy={live(job)} version={p.version}
                      onFitSnapshot={(s) => p.onFitSnapshot(name, s)} onOpenInPlots={p.onOpenInPlots} />
                  </td></tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
