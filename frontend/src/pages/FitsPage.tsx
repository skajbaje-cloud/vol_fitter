import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { FitsTable } from "../components/FitsTable";
import { Seg } from "../components/Seg";
import { type MenuItem, SelectMenu } from "../components/SelectMenu";
import { fmtPct, fmtTime } from "../lib/format";
import type { FitCoverage, JobOut, NameOut, SeriesSpec } from "../types";

interface Props {
  names: NameOut[];                       // names with at least one priced snapshot
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

const SCOPES = [
  { value: "latest" as const, label: "Latest snapshot" },
  { value: "unfitted" as const, label: "Every unfitted snapshot" },
];
const live = (j: JobOut) => j.status === "queued" || j.status === "running";

export function FitsPage({ names, onOpenInPlots }: Props) {
  const [coverage, setCoverage] = useState<FitCoverage[]>([]);
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [scope, setScope] = useState<"latest" | "unfitted">("latest");
  const [anchor, setAnchor] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const doneSeen = useRef(-1);

  const loadCoverage = useCallback(() => api.fitCoverage().then(setCoverage, (e: Error) => setError(e.message)), []);
  const loadJobs = useCallback(() => api.jobs().then((all) => setJobs(all.filter((j) => j.kind === "fit")), (e: Error) => setError(e.message)), []);
  useEffect(() => { loadCoverage(); loadJobs(); }, [loadCoverage, loadJobs, names]);

  const busy = jobs.some(live);
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(loadJobs, 2000);
    return () => clearInterval(t);
  }, [busy, loadJobs]);

  // When fits finish: re-read coverage, drop cached smiles (their params changed), refresh open details.
  const nDone = jobs.filter((j) => j.status === "done" || j.status === "failed").length;
  useEffect(() => {
    if (doneSeen.current >= 0 && nDone > doneSeen.current) {
      api.forgetSmiles();
      loadCoverage();
      setVersion((v) => v + 1);
    }
    doneSeen.current = nDone;
  }, [nDone, loadCoverage]);

  const byName = useMemo(() => {
    const m = new Map<string, FitCoverage[]>();
    for (const c of coverage) m.set(c.name, [...(m.get(c.name) ?? []), c]);
    for (const list of m.values()) list.sort((a, b) => b.snapshot_ts.localeCompare(a.snapshot_ts));
    return m;
  }, [coverage]);
  const list = names.map((n) => n.name);
  const lastJob = (name: string) => jobs.find((j) => j.name === name);

  const pick = (keys: string[]) => setSelected(new Set(keys));
  const groups = [...new Set(names.map((n) => n.group_name).filter((g): g is string => !!g))].sort();
  const latestUnfitted = list.filter((n) => (byName.get(n)?.[0]?.n_fitted ?? 0) === 0);
  const anyUnfitted = list.filter((n) => (byName.get(n) ?? []).some((c) => c.n_fitted === 0));
  const menu: MenuItem[] = [
    { label: `All (${list.length})`, onSelect: () => pick(list) },
    { label: "None", onSelect: () => pick([]) },
    { label: `Latest snapshot not fitted (${latestUnfitted.length})`, divider: true, onSelect: () => pick(latestUnfitted) },
    { label: `Any unfitted snapshot (${anyUnfitted.length})`, onSelect: () => pick(anyUnfitted) },
    ...groups.map((g, i) => ({ label: `Group: ${g}`, divider: i === 0, onSelect: () => pick(names.filter((n) => n.group_name === g).map((n) => n.name)) })),
  ];

  async function submit(fn: () => Promise<JobOut[]>) {
    setError("");
    try { await fn(); await loadJobs(); } catch (e) { setError((e as Error).message); }
  }
  const nSel = list.filter((n) => selected.has(n)).length;
  const runSelected = () => (nSel ? submit(() => api.runFits(list.filter((n) => selected.has(n)), scope, anchor))
    : setError("Tick at least one name first (the Select menu has shortcuts)."));

  return (
    <>
      <div className="panel">
        <div className="names-bar">
          <SelectMenu items={menu} />
          <span className="muted">{nSel} selected</span>
          <Seg label="What to fit" value={scope} options={SCOPES} onChange={setScope} />
          <label className="check-label" title="Start each expiry from the previous snapshot's fit (and anchor to it if configured)">
            <input type="checkbox" checked={anchor} onChange={(e) => setAnchor(e.target.checked)} /> Start from previous fit
          </label>
          <span className="spacer" />
          {error && <span className="error-text">{error}</span>}
          <button type="button" className="btn" onClick={runSelected}>Fit {nSel || ""} name{nSel === 1 ? "" : "s"}</button>
        </div>
        {list.length === 0 ? <div className="muted empty">No priced snapshots yet. Run one from the Snapshot page.</div> : (
          <FitsTable names={list} coverage={byName} selected={selected} expanded={expanded} lastJob={lastJob} version={version}
            onToggle={(n) => setSelected((s) => { const t = new Set(s); if (t.has(n)) t.delete(n); else t.add(n); return t; })}
            onToggleAll={() => pick(nSel === list.length ? [] : list)} onExpand={setExpanded}
            onFitSnapshot={(n, s) => submit(() => api.runFits([n], "snapshot", anchor, s))} onOpenInPlots={onOpenInPlots} />
        )}
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panel-head">Fit runs {busy && <span className="muted">· refreshing every 2s</span>}</div>
        {jobs.length === 0 ? <div className="muted empty">No fits since the server started.</div> : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Name</th><th>Status</th><th>Snapshots</th><th>Expiries ok</th><th>Mean inside</th><th>Worst</th><th>Duration</th><th>Submitted</th></tr></thead>
              <tbody>
                {jobs.map((j) => {
                  const f = j.fit ?? [];
                  const ok = f.reduce((a, x) => a + x.n_ok, 0), tot = f.reduce((a, x) => a + x.n_expiries, 0);
                  const worst = f.length ? Math.min(...f.map((x) => x.min_pct_inside ?? 1)) : null;
                  const mean = tot ? f.reduce((a, x) => a + (x.mean_pct_inside ?? 0) * x.n_expiries, 0) / tot : null;
                  return (
                    <tr key={j.id}>
                      <td className="name">{j.name}</td>
                      <td><span className={`pill ${j.status}`}><span className="led" />{j.status}</span>
                        {j.error && <div className="error-text">{j.error}</div>}</td>
                      <td>{j.status === "done" ? (f.length || <span className="muted">none to fit</span>) : "—"}</td>
                      <td>{tot ? `${ok}/${tot}` : "—"}</td>
                      <td>{fmtPct(mean, 0)}</td>
                      <td>{fmtPct(worst, 0)}</td>
                      <td>{j.duration_sec != null ? `${j.duration_sec.toFixed(1)}s` : "—"}</td>
                      <td>{fmtTime(j.submitted_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="note">
        Fits use the stored quotes only (no LSEG), on their own worker, so they never wait behind snapshots. "Inside" is
        the share of quotes whose bid-ask the fitted smile passes through. A refit overwrites that snapshot's earlier fit.
      </div>
    </>
  );
}
