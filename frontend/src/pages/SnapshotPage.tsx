import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { JobTable } from "../components/JobTable";
import { Seg } from "../components/Seg";
import type { JobOut, NameOut } from "../types";

const NEW = "__new__";

interface Props {
  names: NameOut[];
  onSnapshotsChanged: () => void;
}

export function SnapshotPage({ names, onSnapshotsChanged }: Props) {
  const [scope, setScope] = useState<"single" | "universe">("single");
  const [underlying, setUnderlying] = useState(names[0]?.name ?? NEW);
  const [newName, setNewName] = useState("");
  const [newChain, setNewChain] = useState("");
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(() => api.jobs().then(setJobs, (e: Error) => setError(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);

  // Poll only while something is queued or running; tell the app when a run lands.
  const busy = jobs.some((j) => j.status === "queued" || j.status === "running");
  const doneCount = jobs.filter((j) => j.status === "done").length;
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [busy, refresh]);
  useEffect(() => { if (doneCount) onSnapshotsChanged(); }, [doneCount, onSnapshotsChanged]);

  async function run() {
    setError("");
    setSubmitting(true);
    try {
      if (scope === "universe") await api.runSnapshot({ scope });
      else if (underlying === NEW) await api.runSnapshot({ scope, underlying: newName.trim(), chain_ric: newChain.trim() });
      else await api.runSnapshot({ scope, underlying });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const activeCount = names.filter((n) => n.active).length;
  const canRun = scope === "universe" || underlying !== NEW || (newName.trim() && newChain.trim());

  return (
    <>
      <div className="card-row">
        <div className="stat-card"><div className="label">Names tracked</div><div className="value">{names.length}</div>
          <div className="sub">{activeCount} active</div></div>
        <div className="stat-card"><div className="label">Runs this session</div><div className="value">{jobs.length}</div>
          <div className="sub">{jobs.filter((j) => j.status === "failed").length} failed</div></div>
        <div className="stat-card"><div className="label">Queue</div><div className="value">{jobs.filter((j) => j.status === "queued" || j.status === "running").length}</div>
          <div className="sub">queued or running</div></div>
      </div>

      <div className="toolbar">
        <div className="field"><span className="field-label">Scope</span>
          <Seg label="Scope" value={scope} onChange={setScope} options={[
            { value: "single", label: "Single underlying" },
            { value: "universe", label: `All active names (${activeCount})` },
          ]} />
        </div>
        {scope === "single" && (
          <label className="field"><span className="field-label">Underlying</span>
            <select value={underlying} onChange={(e) => setUnderlying(e.target.value)}>
              {names.map((n) => <option key={n.name}>{n.name}</option>)}
              <option value={NEW}>New underlying…</option>
            </select>
          </label>
        )}
        {scope === "single" && underlying === NEW && (
          <>
            <label className="field"><span className="field-label">RIC</span>
              <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder=".SPX" /></label>
            <label className="field"><span className="field-label">Chain RIC</span>
              <input value={newChain} onChange={(e) => setNewChain(e.target.value)} placeholder="0#SPX*.U" /></label>
          </>
        )}
        <div className="spacer" />
        <button type="button" className="btn" onClick={run} disabled={!canRun || submitting}>
          {submitting ? "Queuing…" : "Run snapshot"}
        </button>
      </div>
      {error && <div className="note error">{error}</div>}

      <div className="panel">
        <div className="panel-head">Runs {busy && <span className="muted">· refreshing every 2s</span>}</div>
        <JobTable jobs={jobs} />
      </div>
      <div className="note">Needs LSEG Workspace running and signed in on this machine. Runs go one at a time; job history clears when the server restarts.</div>
    </>
  );
}
