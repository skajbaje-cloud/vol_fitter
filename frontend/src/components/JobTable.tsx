import { fmtNum, fmtPct, fmtTime, fmtTs } from "../lib/format";
import type { JobOut } from "../types";

const ICON: Record<JobOut["status"], string> = { queued: "", running: "", done: "✓", failed: "✕" };

export function JobTable({ jobs }: { jobs: JobOut[] }) {
  if (!jobs.length) {
    return <div className="muted empty">No jobs since the server started. Tick names above and snapshot them, or add new ones.</div>;
  }
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th><th>Status</th><th>Spot</th><th>Window vol</th><th>Window</th>
            <th>Quotes</th><th>Expiries</th><th>Duration</th><th>Snapshot</th><th>Submitted</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <td className="name">{j.kind !== "snapshot" && <span className="tag">{j.kind === "lookup" ? "look-up" : "chain check"}</span>}
                {j.origin === "schedule" && <span className="tag" title="Started by the schedule">scheduled</span>}{j.name}
                {j.check && <div className="muted job-sub">{j.check.n_options.toLocaleString()} options · {j.check.n_expiries} expiries</div>}</td>
              <td>
                <span className={`pill ${j.status}`}><span className="led" />{ICON[j.status]} {j.status}</span>
                {j.error && <div className="error-text">{j.error}</div>}
              </td>
              <td>{fmtNum(j.spot, 2)}</td>
              <td>{fmtPct(j.window_vol, 1)}</td>
              <td>{j.window_size?.toLocaleString() ?? "—"}</td>
              <td>{j.n_quotes?.toLocaleString() ?? "—"}</td>
              <td>{j.n_maturities ?? "—"}</td>
              <td>{j.duration_sec != null ? `${j.duration_sec.toFixed(1)}s` : "—"}</td>
              <td>{fmtTs(j.snapshot_ts)}</td>
              <td>{fmtTime(j.submitted_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
