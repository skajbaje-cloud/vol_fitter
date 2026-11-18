import { useState } from "react";
import { type Draft, filled, MAX_SLOTS, WEEKDAYS } from "../lib/schedule";
import { tzAbbr } from "../lib/tz";
import { DAYS, type Day, type ScheduleRow } from "../types";
import { TimeInput } from "./TimeInput";

interface Props {
  selected: ScheduleRow[];
  rows: ScheduleRow[];
  drafts: Record<string, Draft>;
  lead: number;                  // table columns before the snap-times column
  tail: number;                  // and after it
  onApply: (times: string[], days: Day[] | null, mode: "replace" | "add") => string | null;   // an error, if any
}

const empty = () => Array<string>(MAX_SLOTS).fill("");

/** A row at the top of the table: type times once, in the same column as each row's times, and write them into every ticked name. */
export function BulkTimesRow({ selected, rows, drafts, lead, tail, onApply }: Props) {
  const [times, setTimes] = useState<string[]>(empty);
  const [days, setDays] = useState<Day[] | null>(null);       // null = leave each name's days alone
  const [mode, setMode] = useState<"replace" | "add">("replace");
  const [msg, setMsg] = useState("");
  const zones = [...new Set(selected.map((r) => (r.timezone ? tzAbbr(r.timezone) : "no zone")))];
  const dayKey = days?.join(",") ?? "";
  const presets = [WEEKDAYS.join(","), DAYS.join(",")];

  function copyFrom(name: string) {
    const d = drafts[name];
    if (!d) return;
    setTimes([...filled(d), ...empty()].slice(0, MAX_SLOTS));
    setDays(d.days);
    setMsg("");
  }

  function apply() {
    if (mode === "add" && !times.some(Boolean)) { setMsg("Type at least one time to add."); return; }
    setMsg(onApply(times, days, mode) ?? "");
  }

  return (
    <tr className="bulk-row">
      <td colSpan={lead}>
        <b>Set times for {selected.length} ticked</b>
        <div className="muted job-sub">local to each name ({zones.join(", ")})</div>
      </td>
      <td>
        <div className="times-cell">
          {times.map((t, i) => (
            <TimeInput key={i} value={t} label={`Bulk time ${i + 1}`} onChange={(v) => setTimes(times.map((x, j) => (j === i ? v : x)))} />
          ))}
        </div>
      </td>
      <td colSpan={tail}>
        <div className="bulk-controls">
          <select aria-label="Days" value={dayKey} onChange={(e) => setDays(e.target.value ? (e.target.value.split(",") as Day[]) : null)}>
            <option value="">Keep their days</option>
            <option value={presets[0]}>Mon–Fri</option>
            <option value={presets[1]}>Every day</option>
            {days && !presets.includes(dayKey) && <option value={dayKey}>{days.join(" ")}</option>}
          </select>
          <select aria-label="Replace or add" value={mode} onChange={(e) => setMode(e.target.value as "replace" | "add")}>
            <option value="replace">Replace</option>
            <option value="add">Add</option>
          </select>
          <select aria-label="Copy times from a name" value="" onChange={(e) => copyFrom(e.target.value)}>
            <option value="">Copy from…</option>
            {rows.filter((r) => r.timezone).map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
          </select>
          <button type="button" className="btn-secondary btn-xs" onClick={apply}>Apply</button>
        </div>
        {msg && <div className="warn-text job-sub">{msg}</div>}
      </td>
    </tr>
  );
}
