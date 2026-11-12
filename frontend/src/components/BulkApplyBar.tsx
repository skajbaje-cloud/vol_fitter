import { useState } from "react";
import { type Draft, filled, MAX_SLOTS, WEEKDAYS } from "../lib/schedule";
import { tzAbbr } from "../lib/tz";
import { DAYS, type Day, type ScheduleRow } from "../types";
import { TimeInput } from "./TimeInput";

interface Props {
  selected: ScheduleRow[];
  rows: ScheduleRow[];
  drafts: Record<string, Draft>;
  onApply: (times: string[], days: Day[] | null, mode: "replace" | "add") => string | null;   // an error, if any
}

const empty = () => Array<string>(MAX_SLOTS).fill("");

/** Shown while rows are ticked: type times once, write them into every ticked name's draft. */
export function BulkApplyBar({ selected, rows, drafts, onApply }: Props) {
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
    <div className="bulk-bar" role="region" aria-label="Set times for ticked names">
      <b>{selected.length} ticked</b>
      <span className="muted">times</span>
      {times.map((t, i) => (
        <TimeInput key={i} value={t} label={`Bulk time ${i + 1}`} onChange={(v) => setTimes(times.map((x, j) => (j === i ? v : x)))} />
      ))}
      <select aria-label="Days" value={dayKey} onChange={(e) => setDays(e.target.value ? (e.target.value.split(",") as Day[]) : null)}>
        <option value="">Keep each name's days</option>
        <option value={presets[0]}>Mon–Fri</option>
        <option value={presets[1]}>Every day</option>
        {days && !presets.includes(dayKey) && <option value={dayKey}>{days.join(" ")}</option>}
      </select>
      <select aria-label="Replace or add" value={mode} onChange={(e) => setMode(e.target.value as "replace" | "add")}>
        <option value="replace">Replace their times</option>
        <option value="add">Add to their times</option>
      </select>
      <select aria-label="Copy times from a name" value="" onChange={(e) => copyFrom(e.target.value)}>
        <option value="">Copy from…</option>
        {rows.filter((r) => r.timezone).map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
      </select>
      <button type="button" className="btn-secondary" onClick={apply}>Apply</button>
      <span className={msg ? "warn-text" : "muted"}>{msg || `Local to each name (${zones.join(", ")}). Nothing is saved until you save.`}</span>
    </div>
  );
}
