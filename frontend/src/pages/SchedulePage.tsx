import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { BulkApplyBar } from "../components/BulkApplyBar";
import { LoadStrip } from "../components/LoadStrip";
import { ScheduleTable } from "../components/ScheduleTable";
import { SchedulerStatus } from "../components/SchedulerStatus";
import { type MenuItem, SelectMenu } from "../components/SelectMenu";
import { type Draft, applyBulk, filled, fromRow, loadBuckets, sameDraft, toItem, validate } from "../lib/schedule";
import { tzAbbr } from "../lib/tz";
import type { Day, NameOut, ScheduleRow, SchedulerStatus as Status } from "../types";

const STATUS_POLL_MS = 20_000;

/** names: re-read the schedule whenever the names list changes (e.g. a time zone set on the Snapshot tab). */
export function SchedulePage({ names }: { names: NameOut[] }) {
  const [rows, setRows] = useState<ScheduleRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [status, setStatus] = useState<Status | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const adopt = useCallback((fresh: ScheduleRow[]) => {
    setRows(fresh);
    setDrafts(Object.fromEntries(fresh.map((r) => [r.name, fromRow(r)])));
  }, []);
  const loadStatus = useCallback(() => api.schedulerStatus().then(setStatus, (e: Error) => setError(e.message)), []);
  const load = useCallback(() => api.schedule().then((s) => adopt(s.names), (e: Error) => setError(e.message)), [adopt]);
  useEffect(() => { load(); loadStatus(); }, [load, loadStatus, names]);
  useEffect(() => {
    const t = setInterval(loadStatus, STATUS_POLL_MS);
    return () => clearInterval(t);
  }, [loadStatus]);

  const dirty = rows.filter((r) => drafts[r.name] && !sameDraft(drafts[r.name], fromRow(r)));
  const invalid = dirty.filter((r) => validate(drafts[r.name]).errors.length);
  const buckets = useMemo(() => loadBuckets(rows, drafts), [rows, drafts]);
  const selRows = rows.filter((r) => selected.has(r.name));

  const pick = (names: string[]) => setSelected(new Set(names));
  const groups = [...new Set(rows.map((r) => r.group_name).filter((g): g is string => !!g))].sort();
  const zones = [...new Set(rows.map((r) => r.timezone).filter((z): z is string => !!z))].sort();
  const menu: MenuItem[] = [
    { label: `All active (${rows.filter((r) => r.active).length})`, onSelect: () => pick(rows.filter((r) => r.active).map((r) => r.name)) },
    { label: "None", onSelect: () => pick([]) },
    ...groups.map((g, i) => ({ label: `Group: ${g}`, divider: i === 0, onSelect: () => pick(rows.filter((r) => r.group_name === g).map((r) => r.name)) })),
    ...zones.map((z, i) => ({ label: `Zone: ${z} (${tzAbbr(z)})`, divider: i === 0, onSelect: () => pick(rows.filter((r) => r.timezone === z).map((r) => r.name)) })),
    { label: "No times set", divider: true, onSelect: () => pick(rows.filter((r) => r.timezone && !filled(drafts[r.name] ?? fromRow(r)).length).map((r) => r.name)) },
  ];

  function bulkApply(times: string[], days: Day[] | null, mode: "replace" | "add"): string | null {
    const zoneless = selRows.filter((r) => !r.timezone).map((r) => r.name);
    const target = selRows.filter((r) => r.timezone).map((r) => r.name);
    const { next, overflow } = applyBulk(drafts, target, times, days, mode);
    setDrafts(next);
    const msgs = [];
    if (overflow.length) msgs.push(`Would pass 5 times, left unchanged: ${overflow.join(", ")}`);
    if (zoneless.length) msgs.push(`No time zone, skipped: ${zoneless.join(", ")}`);
    return msgs.length ? `${msgs.join(". ")}.` : null;
  }

  async function save() {
    setError(""); setNote("");
    if (invalid.length) { setError(`Fix the times for ${invalid.map((r) => r.name).join(", ")} first.`); return; }
    setSaving(true);
    try {
      const out = await api.saveSchedule(dirty.map((r) => toItem(r.name, drafts[r.name])));
      adopt(out.names);
      setNote(`Saved ${dirty.length} name${dirty.length === 1 ? "" : "s"}.`);
      await loadStatus();
    } catch (e) { setError((e as Error).message); } finally { setSaving(false); }
  }

  async function pause(paused: boolean) {
    try { setStatus(await api.pauseScheduler(paused)); } catch (e) { setError((e as Error).message); }
  }

  return (
    <>
      <div className="panel">
        <SchedulerStatus status={status} busy={saving} onPause={pause} />
        <LoadStrip buckets={buckets} />
      </div>
      <div className="panel" style={{ marginTop: 14 }}>
        <div className="names-bar">
          <SelectMenu items={menu} />
          <span className="muted">{selected.size} selected · times are typed in each name's own time zone</span>
        </div>
        {selRows.length > 0 && <BulkApplyBar selected={selRows} rows={rows} drafts={drafts} onApply={bulkApply} />}
        <ScheduleTable rows={rows} drafts={drafts} selected={selected} expanded={expanded}
          onToggle={(n) => setSelected((s) => { const t = new Set(s); if (t.has(n)) t.delete(n); else t.add(n); return t; })}
          onToggleAll={() => pick(selected.size === rows.length ? [] : rows.map((r) => r.name))}
          onChange={(n, d) => setDrafts((all) => ({ ...all, [n]: d }))} onExpand={setExpanded} />
        <div className="names-foot">
          {error ? <span className="error-text">{error}</span>
            : <span className={dirty.length ? "warn-text" : "muted"}>{dirty.length ? `${dirty.length} unsaved change${dirty.length === 1 ? "" : "s"}` : note}</span>}
          <button type="button" className="btn-secondary" disabled={!dirty.length || saving}
            onClick={() => { adopt(rows); setNote(""); setError(""); }}>Discard</button>
          <button type="button" className="btn" disabled={!dirty.length || saving} onClick={save}>{saving ? "Saving…" : "Save schedule"}</button>
        </div>
      </div>
      <div className="note">
        Schedules fire only while this server is running and LSEG Workspace is open. Snapshots run one at a time, so names
        set for the same moment snap one after another. A firing missed by more than 15 minutes (server down) is recorded
        as missed, not run late.
      </div>
    </>
  );
}
