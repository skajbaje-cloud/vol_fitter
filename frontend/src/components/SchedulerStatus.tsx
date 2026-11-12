import { useState } from "react";
import { hhmmIn, utcDate } from "../lib/tz";
import type { SchedulerStatus as Status } from "../types";

interface Props { status: Status | null; busy: boolean; onPause: (paused: boolean) => void }

const PILL: Record<string, string> = { queued: "queued", done: "done", failed: "failed", missed: "failed", skipped_busy: "warn" };

export function SchedulerStatus({ status, busy, onPause }: Props) {
  const [open, setOpen] = useState(false);
  if (!status) return null;
  const next = status.upcoming[0];
  const sameTime = next ? status.upcoming.filter((u) => u.fire_utc === next.fire_utc) : [];
  const state = !status.enabled ? ["failed", "Scheduler off in this server"] : status.paused ? ["warn", "Paused"] : ["done", "Running"];

  return (
    <div className="sched-status">
      <div className="sched-status-row">
        <span className={`pill ${state[0]}`}><span className="led" />{state[1]}</span>
        <span className="muted">
          {!status.enabled ? "Start uvicorn without VOL_FITTER_SCHEDULER=off to fire schedules."
            : next ? `Next: ${sameTime.map((u) => u.name).join(", ")} at ${next.local_label} (${hhmmIn(utcDate(next.fire_utc))} your time)`
            : "Nothing scheduled in the next few days."}
        </span>
        <span className="spacer" />
        <button type="button" className="btn-secondary" disabled={busy} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          Recent runs ({status.recent_runs.length})
        </button>
        <button type="button" className="btn-secondary" disabled={busy} onClick={() => onPause(!status.paused)}>
          {status.paused ? "Resume all" : "Pause all"}
        </button>
      </div>
      {open && (
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Scheduled</th><th>Your time</th><th>Status</th><th>Job</th><th>Reason</th></tr></thead>
            <tbody>
              {status.recent_runs.length === 0 && <tr><td colSpan={6} className="muted">No scheduled runs yet.</td></tr>}
              {status.recent_runs.map((r) => (
                <tr key={`${r.name}-${r.scheduled_for_utc}`}>
                  <td className="name">{r.name}</td>
                  <td>{r.local_label ?? "—"} <span className="muted">{r.scheduled_for_utc.slice(0, 10)}</span></td>
                  <td>{hhmmIn(utcDate(r.scheduled_for_utc))}</td>
                  <td><span className={`pill ${PILL[r.status] ?? ""}`}><span className="led" />{r.status.replace("_", " ")}</span></td>
                  <td>{r.job_id ?? "—"}</td>
                  <td className="txt">{r.reason ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
