// Client-side state for the Schedule tab: staged drafts per name, validation and bulk apply.
import type { Day, ScheduleItemIn, ScheduleRow } from "../types";
import { todayIn, wallToInstant } from "./tz";

export const MAX_SLOTS = 5;          // mirrors config.SCHEDULE_MAX_SLOTS
export const MIN_GAP_MIN = 10;       // mirrors config.SCHEDULE_MIN_GAP_MIN
export const WEEKDAYS: Day[] = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

export interface Draft { times: string[]; days: Day[]; enabled: boolean }   // times: always MAX_SLOTS long, "" = empty

const pad = (t: string[]) => [...t, ...Array(MAX_SLOTS).fill("")].slice(0, MAX_SLOTS);
export const filled = (d: Draft) => d.times.filter(Boolean);
export const fromRow = (r: ScheduleRow): Draft => ({ times: pad(r.times), days: r.days, enabled: r.enabled });

/** Sorted, de-duplicated, empty slots last. */
export const normalise = (d: Draft): Draft => ({ ...d, times: pad([...new Set(filled(d))].sort()) });

export function sameDraft(a: Draft, b: Draft): boolean {
  const x = normalise(a), y = normalise(b);
  return x.enabled === y.enabled && x.times.join() === y.times.join() && [...x.days].sort().join() === [...y.days].sort().join();
}

const minutes = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));

export function validate(d: Draft): { errors: string[]; warnings: string[] } {
  const t = filled(d), errors: string[] = [], warnings: string[] = [];
  const bad = t.filter((x) => !TIME_RE.test(x));
  if (bad.length) errors.push(`Not a 24-hour time: ${bad.join(", ")}`);
  if (new Set(t).size !== t.length) errors.push("The same time appears twice");
  if (t.length && !d.days.length) errors.push("Pick at least one day");
  const sorted = [...new Set(t)].filter((x) => TIME_RE.test(x)).sort();
  for (let i = 1; i < sorted.length; i++) {
    if (minutes(sorted[i]) - minutes(sorted[i - 1]) < MIN_GAP_MIN) warnings.push(`${sorted[i - 1]} and ${sorted[i]} are under ${MIN_GAP_MIN} min apart`);
  }
  return { errors, warnings };
}

/** Write the same times (and days) into several drafts; "add" merges and reports names that would pass 5. */
export function applyBulk(drafts: Record<string, Draft>, names: string[], times: string[], days: Day[] | null,
  mode: "replace" | "add"): { next: Record<string, Draft>; overflow: string[] } {
  const next = { ...drafts }, overflow: string[] = [], want = times.filter(Boolean);
  for (const n of names) {
    const cur = drafts[n];
    const merged = mode === "add" ? [...new Set([...filled(cur), ...want])].sort() : [...new Set(want)].sort();
    if (merged.length > MAX_SLOTS) { overflow.push(n); continue; }
    next[n] = { ...cur, times: pad(merged), days: days ?? cur.days };
  }
  return { next, overflow };
}

export const toItem = (name: string, d: Draft): ScheduleItemIn => {
  const n = normalise(d);
  return { name, times: filled(n), days: n.days, enabled: n.enabled };
};

export interface LoadBucket { at: Date; names: string[]; estSec: number }

/** Today's firings (each name's own local today), grouped by instant, for the load strip. */
export function loadBuckets(rows: ScheduleRow[], drafts: Record<string, Draft>, now = new Date()): LoadBucket[] {
  const byMinute = new Map<number, LoadBucket>();
  for (const r of rows) {
    const d = drafts[r.name];
    if (!r.timezone || !r.active || !d?.enabled) continue;
    for (const t of filled(d)) {
      if (!TIME_RE.test(t)) continue;
      const at = wallToInstant(r.timezone, todayIn(r.timezone, now), t);
      const key = Math.round(at.getTime() / 60000);
      const b = byMinute.get(key) ?? { at, names: [], estSec: 0 };
      b.names.push(r.name);
      b.estSec += r.est_duration_sec ?? 60;
      byMinute.set(key, b);
    }
  }
  return [...byMinute.values()].sort((a, b) => a.at.getTime() - b.at.getTime());
}
