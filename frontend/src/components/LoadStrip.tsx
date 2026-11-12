import { type LoadBucket } from "../lib/schedule";
import { hhmmIn, tzAbbr, userZone } from "../lib/tz";

const BUSY_SEC = 300;     // a firing whose queue runs past 5 minutes is drawn amber

/** 24-hour strip in the viewer's own time: one bar per firing instant, taller when more names fire together. */
export function LoadStrip({ buckets }: { buckets: LoadBucket[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.names.length));
  const zone = userZone();
  const minuteOfDay = (d: Date) => {
    const [h, m] = hhmmIn(d).split(":").map(Number);
    return h * 60 + m;
  };
  const nowPct = (minuteOfDay(new Date()) / 1440) * 100;

  return (
    <div className="load-strip">
      <div className="load-axis muted">
        {["00:00", "06:00", "12:00", "18:00"].map((t) => <span key={t}>{t}</span>)}
        <span>24:00 · your time ({tzAbbr(zone)})</span>
      </div>
      <div className="load-track" role="img"
        aria-label={`${buckets.length} snapshot times today; busiest fires ${max} name${max === 1 ? "" : "s"} together`}>
        <div className="load-now" style={{ left: `${nowPct}%` }} title={`Now ${hhmmIn(new Date())}`} />
        {buckets.map((b) => {
          const mins = Math.round(b.estSec / 60);
          return (
            <div key={b.at.getTime()} className={`load-bar ${b.estSec > BUSY_SEC ? "busy" : ""}`}
              style={{ left: `${(minuteOfDay(b.at) / 1440) * 100}%`, height: `${25 + 75 * (b.names.length / max)}%` }}
              title={`${hhmmIn(b.at)} your time · ${b.names.join(", ")} · about ${mins} min in the queue`} />
          );
        })}
      </div>
      <div className="muted load-note">
        {buckets.length ? "Bar height is how many names fire together. Amber: the queue runs past 5 minutes, so later names snap late."
          : "No snap times set yet."}
      </div>
    </div>
  );
}
