import { Fragment, useEffect, useRef } from "react";
import { type Draft, filled, fromRow, sameDraft, validate } from "../lib/schedule";
import { hhmmIn, offsetLabel, todayIn, tzAbbr, utcDate, wallToInstant } from "../lib/tz";
import { DAYS, type ScheduleRow } from "../types";
import { TimeInput } from "./TimeInput";

interface Props {
  rows: ScheduleRow[];
  drafts: Record<string, Draft>;
  selected: Set<string>;
  expanded: string | null;
  onToggle: (name: string) => void;
  onToggleAll: () => void;
  onChange: (name: string, d: Draft) => void;
  onExpand: (name: string | null) => void;
}

const RUN_PILL: Record<string, string> = { queued: "queued", done: "done", failed: "failed", missed: "failed", skipped_busy: "warn" };
const NO_ZONE = "No time zone set";
const COLS = 11;

function groups(rows: ScheduleRow[]): [string, ScheduleRow[]][] {
  const m = new Map<string, ScheduleRow[]>();
  for (const r of rows) m.set(r.timezone ?? NO_ZONE, [...(m.get(r.timezone ?? NO_ZONE) ?? []), r]);
  return [...m.entries()].sort(([a], [b]) => (a === NO_ZONE ? 1 : b === NO_ZONE ? -1 : a.localeCompare(b)));
}

export function ScheduleTable(p: Props) {
  const all = useRef<HTMLInputElement>(null);
  const n = p.rows.filter((r) => p.selected.has(r.name)).length;
  useEffect(() => { if (all.current) all.current.indeterminate = n > 0 && n < p.rows.length; }, [n, p.rows.length]);
  const now = new Date();

  return (
    <div className="table-scroll">
      <table className="data-table names-table sched-table">
        <thead>
          <tr>
            <th className="sel"><input ref={all} type="checkbox" aria-label="Select all names"
              checked={p.rows.length > 0 && n === p.rows.length} onChange={p.onToggleAll} /></th>
            <th>Name</th><th>Zone</th>{[1, 2, 3, 4, 5].map((i) => <th key={i}>Time {i}</th>)}<th>Next snap</th><th>Last run</th><th>On</th>
          </tr>
        </thead>
        <tbody>
          {groups(p.rows).map(([zone, rows]) => (
            <Fragment key={zone}>
              <tr className="section"><td colSpan={COLS}>
                {zone === NO_ZONE ? `${NO_ZONE} · set one in the Snapshot tab's row editor before adding times`
                  : `${zone} · ${tzAbbr(zone, now)} · ${offsetLabel(zone, now)} now · ${hhmmIn(now, zone)} local`}
              </td></tr>
              {rows.map((r) => <Row key={r.name} r={r} {...p} />)}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({ r, drafts, selected, expanded, onToggle, onChange, onExpand }: Props & { r: ScheduleRow }) {
  const server = fromRow(r);
  const d = drafts[r.name] ?? server;
  const dirty = !sameDraft(d, server);
  const { errors, warnings } = validate(d);
  const zone = r.timezone;
  const abbr = zone ? tzAbbr(zone) : "";
  const setTime = (i: number, v: string) => onChange(r.name, { ...d, times: d.times.map((t, j) => (j === i ? v : t)) });
  const userTime = (t: string) => (zone && /^\d\d:\d\d$/.test(t) ? `${hhmmIn(wallToInstant(zone, todayIn(zone), t))} your time` : "");
  const toggleDay = (day: (typeof DAYS)[number]) =>
    onChange(r.name, { ...d, days: d.days.includes(day) ? d.days.filter((x) => x !== day) : DAYS.filter((x) => x === day || d.days.includes(x)) });
  const open = expanded === r.name;

  return (
    <>
      <tr className={`${dirty ? "dirty" : ""} ${r.active ? "" : "inactive"}`}>
        <td className="sel"><input type="checkbox" aria-label={`Select ${r.name}`} checked={selected.has(r.name)} onChange={() => onToggle(r.name)} /></td>
        <td className="name">
          <button type="button" className="link-btn" aria-expanded={open} title="Days" onClick={() => onExpand(open ? null : r.name)}>{r.name}</button>
          {!r.active && <span className="muted"> · inactive</span>}
          <div className="muted job-sub">{d.days.length === 7 ? "every day" : d.days.join(" ") || "no days"}</div>
        </td>
        <td>{abbr || "—"}</td>
        {d.times.map((t, i) => (
          <td key={i}>
            <TimeInput value={t} changed={t !== server.times[i]} disabled={!zone} title={userTime(t)}
              label={`${r.name} time ${i + 1}${abbr ? ` (${abbr})` : ""}`} onChange={(v) => setTime(i, v)} />
          </td>
        ))}
        <td>{nextCell(r, dirty)}</td>
        <td>{r.last_run ? <span className={`pill ${RUN_PILL[r.last_run.status] ?? ""}`} title={r.last_run.reason ?? ""}>
          <span className="led" />{r.last_run.status.replace("_", " ")} {r.last_run.local_label ?? ""}</span> : <span className="muted">—</span>}</td>
        <td><button type="button" role="switch" aria-checked={d.enabled} aria-label={`${r.name} schedule on`}
          className={`switch ${d.enabled ? "on" : ""}`} onClick={() => onChange(r.name, { ...d, enabled: !d.enabled })} /></td>
      </tr>
      {(errors.length > 0 || warnings.length > 0) && (
        <tr className="sched-msg"><td /><td colSpan={COLS - 1}>
          {errors.map((e) => <span key={e} className="error-text">{e}. </span>)}
          {warnings.map((w) => <span key={w} className="warn-text">{w}. </span>)}
        </td></tr>
      )}
      {open && (
        <tr className="editor-row"><td /><td colSpan={COLS - 1}>
          <div className="sched-days" role="group" aria-label={`${r.name} days`}>
            <span className="field-label">Days</span>
            {DAYS.map((day) => (
              <button key={day} type="button" aria-pressed={d.days.includes(day)} className={d.days.includes(day) ? "active" : ""}
                onClick={() => toggleDay(day)}>{day}</button>
            ))}
            <span className="muted">{filled(d).length} of 5 times set{zone ? ` · times are ${zone} wall-clock` : ""}</span>
          </div>
        </td></tr>
      )}
    </>
  );
}

function nextCell(r: ScheduleRow, dirty: boolean) {
  if (dirty) return <span className="muted">after saving</span>;
  if (!r.next_fire_utc) return <span className="muted">{r.timezone ? "no times set" : "—"}</span>;
  const at = utcDate(r.next_fire_utc);
  const day = at.toDateString() === new Date().toDateString() ? "" : `${at.toLocaleDateString(undefined, { weekday: "short" })} `;
  return <>{r.next_fire_label}<div className="muted job-sub">{day}{hhmmIn(at)} your time</div></>;
}
