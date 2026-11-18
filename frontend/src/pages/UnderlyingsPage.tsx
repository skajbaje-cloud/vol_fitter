import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { BulkApplyBar } from "../components/BulkApplyBar";
import type { CheckView } from "../components/NameEditor";
import { SchedulerStatus } from "../components/SchedulerStatus";
import { type MenuItem, SelectMenu } from "../components/SelectMenu";
import { UnderlyingsTable } from "../components/UnderlyingsTable";
import {
  type PendingName, applyLookup, checkSummary, isToday, nameKey, newPending, parseRics, pendingKey, pendingState,
} from "../lib/names";
import { type Draft, applyBulk, filled, fromRow, sameDraft, toItem, validate } from "../lib/schedule";
import type { Day, FitCoverage, JobOut, NameOut, NamePatch, ScheduleRow, SchedulerStatus as Status, SeriesSpec } from "../types";

interface Props {
  names: NameOut[];
  onNamesChanged: () => Promise<unknown>;
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

const live = (j?: JobOut) => !!j && (j.status === "queued" || j.status === "running");
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
const STATUS_POLL_MS = 20_000;

/** One row per underlying: register, snap, schedule, fit and delete, all from here. */
export function UnderlyingsPage({ names, onNamesChanged, onOpenInPlots }: Props) {
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [pending, setPending] = useState<PendingName[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [addText, setAddText] = useState("");
  const [checks, setChecks] = useState<Record<string, number>>({});   // name -> chain-check job id
  const [coverage, setCoverage] = useState<FitCoverage[]>([]);
  const [version, setVersion] = useState(0);
  const [schedRows, setSchedRows] = useState<ScheduleRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [status, setStatus] = useState<Status | null>(null);
  const [showBulk, setShowBulk] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const fail = useCallback((e: unknown) => setError((e as Error).message), []);

  // ---- loading ----
  const refreshJobs = useCallback(() => api.jobs().then(setJobs, fail), [fail]);
  const loadCoverage = useCallback(() => api.fitCoverage().then(setCoverage, fail), [fail]);
  const loadStatus = useCallback(() => api.schedulerStatus().then(setStatus, fail), [fail]);
  // A reload keeps schedule edits the user hasn't saved yet (e.g. a snapshot finishing mid-edit).
  const rowsRef = useRef<ScheduleRow[]>([]);
  const adopt = useCallback((fresh: ScheduleRow[], keepEdits: boolean) => {
    const old = new Map(rowsRef.current.map((r) => [r.name, r]));
    rowsRef.current = fresh;
    setSchedRows(fresh);
    setDrafts((prev) => Object.fromEntries(fresh.map((r) => {
      const o = old.get(r.name), d = prev[r.name];
      return [r.name, keepEdits && o && d && !sameDraft(d, fromRow(o)) ? d : fromRow(r)];
    })));
  }, []);
  const loadSchedule = useCallback(() => api.schedule().then((s) => adopt(s.names, true), fail), [adopt, fail]);

  useEffect(() => { refreshJobs(); }, [refreshJobs]);
  useEffect(() => { loadCoverage(); loadSchedule(); }, [names, loadCoverage, loadSchedule]);
  useEffect(() => {
    loadStatus();
    const t = setInterval(loadStatus, STATUS_POLL_MS);
    return () => clearInterval(t);
  }, [loadStatus]);

  const busy = jobs.some(live);
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(refreshJobs, 2000);
    return () => clearInterval(t);
  }, [busy, refreshJobs]);

  // Finished snapshots change the names list; finished fits change coverage and the cached smiles.
  const nSnapsDone = jobs.filter((j) => j.kind === "snapshot" && j.status === "done").length;
  useEffect(() => { if (nSnapsDone) onNamesChanged(); }, [nSnapsDone, onNamesChanged]);
  const nFitsDone = jobs.filter((j) => j.kind === "fit" && (j.status === "done" || j.status === "failed")).length;
  const fitsSeen = useRef(-1);
  useEffect(() => {
    if (fitsSeen.current >= 0 && nFitsDone > fitsSeen.current) {
      api.forgetSmiles();
      loadCoverage();
      setVersion((v) => v + 1);
    }
    fitsSeen.current = nFitsDone;
  }, [nFitsDone, loadCoverage]);

  const jobById = useMemo(() => new Map(jobs.map((j) => [j.id, j])), [jobs]);
  const lastJob = useCallback((name: string, kind: JobOut["kind"]) => jobs.find((j) => j.name === name && j.kind === kind), [jobs]);

  // Fold finished look-ups into their pending rows; ready rows get ticked, known names get ticked in the table.
  useEffect(() => {
    const known: string[] = [], ticks: string[] = [], choose: string[] = [];
    let changed = false;
    const next = pending.flatMap((r) => {
      const job = r.lookupJob != null ? jobById.get(r.lookupJob) : undefined;
      if (r.lookup || r.lookupError || !job || live(job)) return [r];
      changed = true;
      if (job.status === "failed") return [{ ...r, lookupError: job.error ?? "Look-up failed." }];
      const hit = job.lookup?.find((l) => l.ric === r.ric);
      if (!hit) return [{ ...r, lookupError: "No result from LSEG." }];
      if (hit.registered) { known.push(r.ric); return []; }
      const row = applyLookup(r, hit);
      if (pendingState(row) === "ready") ticks.push(pendingKey(row.ric));
      if (pendingState(row) === "choose") choose.push(pendingKey(row.ric));
      return [row];
    });
    if (!changed) return;
    setPending(next);
    if (choose.length) setExpanded((e) => e ?? choose[0]);
    if (ticks.length || known.length) setSelected((s) => new Set([...s, ...ticks, ...known.map(nameKey)]));
    if (known.length) setNote(`Already registered, ticked below: ${known.join(", ")}.`);
  }, [jobById, pending]);

  // ---- derived ----
  const byName = useMemo(() => {
    const m = new Map<string, FitCoverage[]>();
    for (const c of coverage) m.set(c.name, [...(m.get(c.name) ?? []), c]);
    for (const list of m.values()) list.sort((a, b) => b.snapshot_ts.localeCompare(a.snapshot_ts));
    return m;
  }, [coverage]);
  const schedule = useMemo(() => new Map(schedRows.map((r) => [r.name, r])), [schedRows]);
  const dirty = schedRows.filter((r) => drafts[r.name] && !sameDraft(drafts[r.name], fromRow(r)));
  const readyPending = pending.filter((r) => pendingState(r) === "ready");
  const selectable = [...readyPending.map((r) => pendingKey(r.ric)), ...names.map((n) => nameKey(n.name))];
  const selPending = readyPending.filter((r) => selected.has(pendingKey(r.ric)));
  const selNames = names.filter((n) => selected.has(nameKey(n.name)));
  const nRun = selPending.length + selNames.length;
  const groups = [...new Set(names.map((n) => n.group_name).filter((g): g is string => !!g))].sort();

  const pick = (keys: string[]) => setSelected(new Set(keys));
  const keys = (list: NameOut[]) => list.map((n) => nameKey(n.name));
  const menu: MenuItem[] = [
    { label: `All active (${names.filter((n) => n.active).length})`, onSelect: () => pick(keys(names.filter((n) => n.active))) },
    { label: "None", onSelect: () => pick([]) },
    ...groups.map((g, i) => ({ label: `Group: ${g}`, divider: i === 0, onSelect: () => pick(keys(names.filter((n) => n.group_name === g))) })),
    { label: "Not snapped today", divider: true, onSelect: () => pick(keys(names.filter((n) => n.active && !isToday(n.last_snapshot_ts)))) },
    { label: "Has unfitted snapshots", onSelect: () => pick(keys(names.filter((n) => (byName.get(n.name) ?? []).some((c) => c.n_fitted === 0)))) },
    { label: "No times set", onSelect: () => pick(keys(names.filter((n) => n.timezone && !filled(drafts[n.name] ?? { times: [], days: [], enabled: true }).length))) },
    ...(readyPending.length ? [{ label: `Pending (${readyPending.length})`, onSelect: () => pick(readyPending.map((r) => pendingKey(r.ric))) }] : []),
  ];

  // ---- actions ----
  async function act(fn: () => Promise<unknown>, okNote = "") {
    setError(""); setNote("");
    try { await fn(); if (okNote) setNote(okNote); } catch (e) { fail(e); }
  }

  async function lookUp() {
    setError(""); setNote("");
    const registered = new Set(names.map((n) => n.name));
    const { rics, bad } = parseRics(addText);
    const known = rics.filter((r) => registered.has(r));
    const fresh = rics.filter((r) => !registered.has(r) && !pending.some((p) => p.ric === r));
    if (bad.length) setError(`Not a RIC: ${bad.join(", ")}`);
    if (known.length) { setSelected((s) => new Set([...s, ...known.map(nameKey)])); setNote(`Already registered, ticked below: ${known.join(", ")}.`); }
    if (!fresh.length) { if (!bad.length && !known.length) setError("Type one or more RICs, e.g. AAPL.O, XLK.P"); return; }
    try {
      const job = await api.lookup(fresh);
      setPending((rows) => [...rows, ...fresh.map((r) => newPending(r, job.id))]);
      setAddText("");
      await refreshJobs();
    } catch (e) { fail(e); }
  }

  async function register(rows: PendingName[]) {
    await api.registerNames(rows.map((r) => ({
      name: r.ric, chain_ric: r.chain, display_name: r.display_name || null,
      group_name: r.group_name || null, expiry_filter: r.expiry_filter, active: r.active, timezone: r.timezone || null,
    })));
    const done = new Set(rows.map((r) => r.ric));
    setPending((all) => all.filter((r) => !done.has(r.ric)));
    setSelected((s) => new Set([...s].map((k) => (k.startsWith("p:") && done.has(k.slice(2)) ? nameKey(k.slice(2)) : k))));
    setExpanded(null);
    await onNamesChanged();
  }

  const snapshot = (list: string[]) => act(async () => { await api.runSnapshots(list); await refreshJobs(); });
  const fit = (list: string[], mode: "unfitted" | "snapshot" = "unfitted", ts?: string) =>
    act(async () => { await api.runFits(list, mode, ts); await refreshJobs(); });

  function snapshotSelected() {
    if (!nRun) { setError("Tick at least one name first (the Select menu has shortcuts)."); return; }
    act(async () => {
      if (selPending.length) await register(selPending);
      await api.runSnapshots([...selNames.map((n) => n.name), ...selPending.map((r) => r.ric)]);
      await refreshJobs();
    });
  }

  function remove(name: string) {
    const ok = window.confirm(`Delete ${name}?\n\nIt disappears from every tab and stops being scheduled. `
      + "Its stored snapshots and fits are kept: adding the RIC again brings them back.");
    if (!ok) return;
    act(async () => {
      await api.deleteName(name);
      setSelected((s) => { const t = new Set(s); t.delete(nameKey(name)); return t; });
      setExpanded(null);
      await onNamesChanged();
    }, `Deleted ${name}.`);
  }

  const saveName = (name: string, patch: NamePatch) => act(async () => { await api.patchName(name, patch); await onNamesChanged(); });

  const check = (name: string, chain: string) =>
    act(async () => { const j = await api.checkChain(name, chain); setChecks((c) => ({ ...c, [name]: j.id })); await refreshJobs(); });

  function checkView(name: string, chain: string): CheckView | null {
    const job = checks[name] != null ? jobById.get(checks[name]) : undefined;
    if (!job) return null;
    if (live(job)) return { busy: true, text: job.status === "queued" ? "Waiting for the running job to finish…" : "Expanding the chain…" };
    if (job.status === "failed") return { busy: false, text: job.error ?? "Check failed.", warn: true };
    const c = job.check!;
    const stale = c.chain_ric !== chain ? ` (for ${c.chain_ric})` : "";
    const m = c.underlying_match;
    return { busy: false, warn: m != null && m < 0.9, text: `${checkSummary(c)}${stale}${m == null ? "" : ` · ${Math.round(m * 100)}% on this underlying`}` };
  }

  function bulkApply(times: string[], days: Day[] | null, mode: "replace" | "add"): string | null {
    const rows = selNames.map((n) => schedule.get(n.name)).filter((r): r is ScheduleRow => !!r);
    const zoneless = rows.filter((r) => !r.timezone).map((r) => r.name);
    const { next, overflow } = applyBulk(drafts, rows.filter((r) => r.timezone).map((r) => r.name), times, days, mode);
    setDrafts(next);
    const msgs = [];
    if (overflow.length) msgs.push(`Would pass 5 times, left unchanged: ${overflow.join(", ")}`);
    if (zoneless.length) msgs.push(`No time zone, skipped: ${zoneless.join(", ")}`);
    return msgs.length ? `${msgs.join(". ")}.` : null;
  }

  async function saveSchedule() {
    const invalid = dirty.filter((r) => validate(drafts[r.name]).errors.length);
    if (invalid.length) { setError(`Fix the times for ${invalid.map((r) => r.name).join(", ")} first.`); return; }
    setSaving(true);
    await act(async () => {
      const out = await api.saveSchedule(dirty.map((r) => toItem(r.name, drafts[r.name])));
      adopt(out.names, false);
      await loadStatus();
    }, `Saved the schedule for ${plural(dirty.length, "name")}.`);
    setSaving(false);
  }

  const pause = (paused: boolean) => act(async () => setStatus(await api.pauseScheduler(paused)));
  const selRows = selNames.map((n) => schedule.get(n.name)).filter((r): r is ScheduleRow => !!r);

  return (
    <div className="panel">
      <SchedulerStatus status={status} busy={saving} onPause={pause} />
      <div className="names-bar">
        <SelectMenu items={menu} />
        <form className="add-rics" onSubmit={(e) => { e.preventDefault(); lookUp(); }}>
          <input value={addText} onChange={(e) => setAddText(e.target.value)} aria-label="Add RICs" placeholder="Add RICs: AAPL.O, XLK.P, .SPX" />
          <button type="submit" className="btn-secondary">Look up</button>
        </form>
        <span className="spacer" />
        <button type="button" className="btn-secondary" aria-expanded={showBulk} disabled={!selRows.length}
          onClick={() => setShowBulk((v) => !v)}>Set times</button>
        <button type="button" className="btn-secondary" disabled={!selNames.length} title="Fit every snapshot not fitted yet"
          onClick={() => fit(selNames.map((n) => n.name))}>Fit {selNames.length || ""}</button>
        <button type="button" className="btn" onClick={snapshotSelected}>Snapshot {nRun || ""}</button>
      </div>
      {showBulk && selRows.length > 0 && <BulkApplyBar selected={selRows} rows={schedRows} drafts={drafts} onApply={bulkApply} />}
      {names.length === 0 && pending.length === 0 ? <div className="muted empty">No underlyings yet. Add some RICs above.</div> : (
        <UnderlyingsTable pending={pending} names={names} coverage={byName} schedule={schedule} drafts={drafts}
          selected={selected} selectable={selectable} expanded={expanded} groups={groups} version={version}
          lastJob={lastJob} checkView={checkView}
          onToggle={(k) => setSelected((s) => { const t = new Set(s); if (t.has(k)) t.delete(k); else t.add(k); return t; })}
          onToggleAll={() => pick(selectable.every((k) => selected.has(k)) ? [] : selectable)}
          onExpand={setExpanded}
          onPendingChange={(ric, patch) => setPending((rows) => rows.map((r) => (r.ric === ric ? { ...r, ...patch } : r)))}
          onRemovePending={(ric) => { setPending((rows) => rows.filter((r) => r.ric !== ric)); setExpanded(null); }}
          onRegister={(row) => act(() => register([row]), `Registered ${row.ric}.`)}
          onSaveName={saveName} onCheck={check}
          onDraft={(n, d) => setDrafts((all) => ({ ...all, [n]: d }))}
          onSnapshot={(n) => snapshot([n])} onFit={(n) => fit([n])} onFitSnapshot={(n, s) => fit([n], "snapshot", s)}
          onDelete={remove} onOpenInPlots={onOpenInPlots} />
      )}
      {(error || note || dirty.length > 0) && (
        <div className="names-foot">
          {error ? <span className="error-text">{error}</span>
            : <span className={dirty.length ? "warn-text" : "muted"}>{dirty.length ? `${plural(dirty.length, "unsaved schedule change")}` : note}</span>}
          {dirty.length > 0 && <>
            <button type="button" className="btn-secondary" disabled={saving} onClick={() => adopt(schedRows, false)}>Discard</button>
            <button type="button" className="btn" disabled={saving} onClick={saveSchedule}>{saving ? "Saving…" : "Save schedule"}</button>
          </>}
        </div>
      )}
    </div>
  );
}
