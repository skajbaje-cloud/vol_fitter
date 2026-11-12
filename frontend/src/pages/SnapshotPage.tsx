import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { JobTable } from "../components/JobTable";
import type { CheckView } from "../components/NameEditor";
import { NamesTable } from "../components/NamesTable";
import { type MenuItem, SelectMenu } from "../components/SelectMenu";
import {
  type PendingName, applyLookup, checkSummary, isToday, nameKey, newPending, parseRics, pendingKey, pendingState,
} from "../lib/names";
import type { JobOut, NameOut, NamePatch } from "../types";

interface Props {
  names: NameOut[];
  onNamesChanged: () => Promise<unknown>;
}

const live = (j?: JobOut) => !!j && (j.status === "queued" || j.status === "running");

export function SnapshotPage({ names, onNamesChanged }: Props) {
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [pending, setPending] = useState<PendingName[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [addText, setAddText] = useState("");
  const [checks, setChecks] = useState<Record<string, number>>({});   // name -> check job id
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(() => api.jobs().then(setJobs, (e: Error) => setError(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);
  const busy = jobs.some(live);
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [busy, refresh]);

  const jobById = useMemo(() => new Map(jobs.map((j) => [j.id, j])), [jobs]);
  const doneSnaps = jobs.filter((j) => j.kind === "snapshot" && j.status === "done").length;
  useEffect(() => { if (doneSnaps) onNamesChanged(); }, [doneSnaps, onNamesChanged]);

  // Fold finished look-ups into their pending rows; ready rows get ticked, known names move to the table.
  useEffect(() => {
    const known: string[] = [];
    const ticks: string[] = [];
    const choose: string[] = [];
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
    if (choose.length) setExpanded((e) => e ?? choose[0]);      // open the chain picker for the first name needing one
    if (ticks.length || known.length) setSelected((s) => new Set([...s, ...ticks, ...known.map(nameKey)]));
    if (known.length) setNote(`Already registered, ticked below: ${known.join(", ")}.`);
  }, [jobById, pending]);

  const registered = new Set(names.map((n) => n.name));
  const groups = [...new Set(names.map((n) => n.group_name).filter((g): g is string => !!g))].sort();
  const readyPending = pending.filter((r) => pendingState(r) === "ready");
  const selectable = [...readyPending.map((r) => pendingKey(r.ric)), ...names.map((n) => nameKey(n.name))];
  const selPending = readyPending.filter((r) => selected.has(pendingKey(r.ric)));
  const selNames = names.filter((n) => selected.has(nameKey(n.name)));
  const nRun = selPending.length + selNames.length;

  const pick = (keys: string[]) => setSelected(new Set(keys));
  const menu: MenuItem[] = [
    { label: `All active (${names.filter((n) => n.active).length})`, onSelect: () => pick(names.filter((n) => n.active).map((n) => nameKey(n.name))) },
    { label: "None", onSelect: () => pick([]) },
    ...groups.map((g, i) => ({ label: `Group: ${g}`, divider: i === 0, onSelect: () => pick(names.filter((n) => n.group_name === g).map((n) => nameKey(n.name))) })),
    { label: "Not snapped today", divider: true, onSelect: () => pick(names.filter((n) => n.active && !isToday(n.last_snapshot_ts)).map((n) => nameKey(n.name))) },
    ...(readyPending.length ? [{ label: `Pending (${readyPending.length})`, onSelect: () => pick(readyPending.map((r) => pendingKey(r.ric))) }] : []),
  ];

  async function lookUp() {
    setError(""); setNote("");
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
      await refresh();
    } catch (e) { setError((e as Error).message); }
  }

  async function run(snapshot: boolean) {
    setError(""); setNote("");
    if (!nRun) { setError("Tick at least one name first (the Select menu has shortcuts)."); return; }
    if (!snapshot && !selPending.length) { setError("Tick a pending name to register."); return; }
    setSubmitting(true);
    try {
      if (selPending.length) {
        await api.registerNames(selPending.map((r) => ({
          name: r.ric, chain_ric: r.chain, display_name: r.display_name || null,
          group_name: r.group_name || null, expiry_filter: r.expiry_filter, active: r.active, timezone: r.timezone || null,
        })));
        const done = new Set(selPending.map((r) => r.ric));
        setPending((rows) => rows.filter((r) => !done.has(r.ric)));
        setSelected((s) => new Set([...s].map((k) => (k.startsWith("p:") && done.has(k.slice(2)) ? nameKey(k.slice(2)) : k))));
        await onNamesChanged();
      }
      if (snapshot) await api.runSnapshots([...selNames.map((n) => n.name), ...selPending.map((r) => r.ric)]);
      else setNote(`Registered ${selPending.map((r) => r.ric).join(", ")}.`);
      await refresh();
    } catch (e) { setError((e as Error).message); } finally { setSubmitting(false); }
  }

  async function saveName(name: string, patch: NamePatch) {
    setError("");
    try { await api.patchName(name, patch); await onNamesChanged(); } catch (e) { setError((e as Error).message); throw e; }
  }

  async function check(name: string, chain: string) {
    try { const j = await api.checkChain(name, chain); setChecks((c) => ({ ...c, [name]: j.id })); await refresh(); }
    catch (e) { setError((e as Error).message); }
  }

  function checkView(name: string, chain: string): CheckView | null {
    const job = checks[name] != null ? jobById.get(checks[name]) : undefined;
    if (!job) return null;
    if (live(job)) return { busy: true, text: job.status === "queued" ? "Waiting for the running job to finish…" : "Expanding the chain…" };
    if (job.status === "failed") return { busy: false, text: job.error ?? "Check failed.", warn: true };
    const c = job.check!;
    const stale = c.chain_ric !== chain ? ` (for ${c.chain_ric})` : "";
    const m = c.underlying_match;
    const warn = m != null && m < 0.9;
    return { busy: false, warn, text: `${checkSummary(c)}${stale}${m == null ? "" : ` · ${Math.round(m * 100)}% on this underlying`}` };
  }

  const snapJobs = jobs.filter((j) => j.kind === "snapshot");
  return (
    <>
      <div className="card-row">
        <div className="stat-card"><div className="label">Names tracked</div><div className="value">{names.length}</div>
          <div className="sub">{names.filter((n) => n.active).length} active</div></div>
        <div className="stat-card"><div className="label">Runs this session</div><div className="value">{snapJobs.length}</div>
          <div className="sub">{snapJobs.filter((j) => j.status === "failed").length} failed</div></div>
        <div className="stat-card"><div className="label">Queue</div><div className="value">{jobs.filter(live).length}</div>
          <div className="sub">queued or running</div></div>
      </div>

      <div className="panel">
        <div className="names-bar">
          <SelectMenu items={menu} />
          <span className="muted">{nRun} selected</span>
          <form className="add-rics" onSubmit={(e) => { e.preventDefault(); lookUp(); }}>
            <input value={addText} onChange={(e) => setAddText(e.target.value)} aria-label="Add RICs" placeholder="Add RICs: AAPL.O, XLK.P, .SPX" />
            <button type="submit" className="btn-secondary">Look up</button>
          </form>
        </div>
        <NamesTable pending={pending} names={names} selected={selected} selectable={selectable} expanded={expanded} groups={groups}
          lastJob={(n) => snapJobs.find((j) => j.name === n)} checkView={checkView}
          onToggle={(k) => setSelected((s) => { const t = new Set(s); if (t.has(k)) t.delete(k); else t.add(k); return t; })}
          onToggleAll={() => pick(selectable.every((k) => selected.has(k)) ? [] : selectable)}
          onExpand={setExpanded}
          onPendingChange={(ric, patch) => setPending((rows) => rows.map((r) => (r.ric === ric ? { ...r, ...patch } : r)))}
          onRemovePending={(ric) => { setPending((rows) => rows.filter((r) => r.ric !== ric)); setExpanded(null); }}
          onSaveName={saveName} onCheck={check} />
        <div className="names-foot">
          {error ? <span className="error-text">{error}</span> : <span className="muted">{note ||
            (selPending.length ? `${selPending.length} pending name${selPending.length > 1 ? "s" : ""} will be registered first.` : "")}</span>}
          {selPending.length > 0 && <button type="button" className="btn-secondary" onClick={() => run(false)} disabled={submitting}>Register only</button>}
          <button type="button" className="btn" onClick={() => run(true)} disabled={submitting}>
            {submitting ? "Queuing…" : `Snapshot ${nRun || ""} name${nRun === 1 ? "" : "s"}`.replace("  ", " ")}
          </button>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panel-head">Runs {busy && <span className="muted">· refreshing every 2s</span>}</div>
        <JobTable jobs={jobs} />
      </div>
      <div className="note">Look-ups, chain checks and snapshots all use LSEG Workspace on this machine, one job at a time; look-ups go first. Job history clears when the server restarts.</div>
    </>
  );
}
