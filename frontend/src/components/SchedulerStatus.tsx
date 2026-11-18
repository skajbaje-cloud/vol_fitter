import { hhmmIn, utcDate } from "../lib/tz";
import type { SchedulerStatus as Status } from "../types";

interface Props { status: Status | null; busy: boolean; onPause: (paused: boolean) => void }

/** One line: is the scheduler running, what fires next, and a pause switch. Past runs are in the Logs tab. */
export function SchedulerStatus({ status, busy, onPause }: Props) {
  if (!status) return null;
  const next = status.upcoming[0];
  const sameTime = next ? status.upcoming.filter((u) => u.fire_utc === next.fire_utc) : [];
  const state = !status.enabled ? ["failed", "Scheduler off"] : status.paused ? ["warn", "Paused"] : ["done", "Scheduler on"];

  return (
    <div className="sched-status">
      <span className={`pill ${state[0]}`}><span className="led" />{state[1]}</span>
      <span className="muted">
        {!status.enabled ? "Start uvicorn without VOL_FITTER_SCHEDULER=off to fire schedules."
          : next ? `Next: ${sameTime.map((u) => u.name).join(", ")} at ${next.local_label} (${hhmmIn(utcDate(next.fire_utc))} your time)`
          : "Nothing scheduled in the next few days."}
      </span>
      <span className="spacer" />
      {status.enabled && (
        <button type="button" className="btn-secondary btn-xs" disabled={busy} onClick={() => onPause(!status.paused)}>
          {status.paused ? "Resume" : "Pause"}
        </button>
      )}
    </div>
  );
}
