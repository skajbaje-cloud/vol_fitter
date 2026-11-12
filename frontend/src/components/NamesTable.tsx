import { Fragment, useEffect, useRef, useState } from "react";
import { fmtTs } from "../lib/format";
import { type PendingName, nameKey, pendingKey, pendingState } from "../lib/names";
import type { JobOut, NameOut, NamePatch } from "../types";
import { type CheckView, type NameDraft, NameEditor } from "./NameEditor";

interface Props {
  pending: PendingName[];
  names: NameOut[];
  selected: Set<string>;
  selectable: string[];                         // keys a "select all" may tick
  expanded: string | null;
  groups: string[];
  lastJob: (name: string) => JobOut | undefined;
  checkView: (name: string, chain: string) => CheckView | null;
  onToggle: (key: string) => void;
  onToggleAll: () => void;
  onExpand: (key: string | null) => void;
  onPendingChange: (ric: string, patch: Partial<PendingName>) => void;
  onRemovePending: (ric: string) => void;
  onSaveName: (name: string, patch: NamePatch) => Promise<void>;
  onCheck: (name: string, chain: string) => void;
}

const STATE_PILL = {
  looking: ["queued", "looking up"], notfound: ["failed", "not found"], choose: ["warn", "choose chain"], ready: ["done", "ready"],
} as const;
const JOB_PILL = { queued: "queued", running: "snapping", done: "snapped", failed: "failed" } as const;
const COLS = 10;

export function NamesTable(p: Props) {
  const all = useRef<HTMLInputElement>(null);
  const nSel = p.selectable.filter((k) => p.selected.has(k)).length;
  useEffect(() => { if (all.current) all.current.indeterminate = nSel > 0 && nSel < p.selectable.length; }, [nSel, p.selectable.length]);
  const toggleRow = (key: string) => p.onExpand(p.expanded === key ? null : key);

  return (
    <div className="table-scroll">
      <table className="data-table names-table">
        <thead>
          <tr>
            <th className="sel"><input ref={all} type="checkbox" aria-label="Select all names"
              checked={p.selectable.length > 0 && nSel === p.selectable.length} onChange={p.onToggleAll} /></th>
            <th>RIC</th><th>Name</th><th>Chain RIC</th><th>Group</th><th>Expiries</th><th>Last snap</th><th>Active</th><th>Status</th><th />
          </tr>
        </thead>
        <tbody>
          {p.pending.length > 0 && <tr className="section"><td colSpan={COLS}>Pending · not in the database yet</td></tr>}
          {p.pending.map((row) => {
            const key = pendingKey(row.ric), st = pendingState(row), [cls, label] = STATE_PILL[st];
            return (
              <Fragment key={key}>
                <tr className={p.expanded === key ? "open" : ""}>
                  <td className="sel"><input type="checkbox" aria-label={`Select ${row.ric}`} disabled={st !== "ready"}
                    title={st === "ready" ? "" : "Pick a chain first"} checked={p.selected.has(key)} onChange={() => p.onToggle(key)} /></td>
                  <td className="name">{row.ric}</td>
                  <td className="txt dname" title={row.display_name}>{row.display_name || "—"}</td>
                  <td>{row.chain || "—"}</td>
                  <td className="txt">{row.group_name || "—"}</td>
                  <td className="txt">{row.expiry_filter === "monthly" ? "monthlies" : "all"}</td>
                  <td>—</td>
                  <td><Toggle on={row.active} label={`${row.ric} active`} onChange={(v) => p.onPendingChange(row.ric, { active: v })} /></td>
                  <td>{row.lookup?.found
                    ? <button type="button" className={`pill pill-btn ${cls}`} aria-expanded={p.expanded === key}
                        title="Choose the chain and edit the details" onClick={() => toggleRow(key)}>
                        <span className="led" />{label} {p.expanded === key ? "▴" : "▾"}</button>
                    : <span className={`pill ${cls}`}><span className="led" />{label}</span>}
                    {st !== "ready" && (row.lookupError || row.lookup?.error) && <div className="error-text">{row.lookupError || row.lookup?.error}</div>}</td>
                  <td><EditBtn open={p.expanded === key} label={row.ric} onClick={() => toggleRow(key)} /></td>
                </tr>
                {p.expanded === key && row.lookup?.found && (
                  <tr className="editor-row"><td colSpan={COLS}>
                    <NameEditor id={key} value={draftOf(row)} candidates={row.lookup.candidates} groups={p.groups}
                      check={p.checkView(row.ric, row.chain)} onCheck={() => p.onCheck(row.ric, row.chain)}
                      onChange={(d) => p.onPendingChange(row.ric, { ...d })}
                      actions={<button type="button" className="btn-secondary" onClick={() => p.onRemovePending(row.ric)}>Remove</button>} />
                  </td></tr>
                )}
              </Fragment>
            );
          })}
          {p.pending.length > 0 && <tr className="section"><td colSpan={COLS}>Registered</td></tr>}
          {p.names.map((n) => {
            const key = nameKey(n.name), job = p.lastJob(n.name);
            return (
              <Fragment key={key}>
                <tr className={`${p.expanded === key ? "open" : ""} ${n.active ? "" : "inactive"}`}>
                  <td className="sel"><input type="checkbox" aria-label={`Select ${n.name}`} checked={p.selected.has(key)} onChange={() => p.onToggle(key)} /></td>
                  <td className="name">{n.name}</td>
                  <td className="txt dname" title={n.display_name ?? ""}>{n.display_name || "—"}</td>
                  <td>{n.chain_ric || "—"}</td>
                  <td className="txt">{n.group_name || "—"}</td>
                  <td className="txt">{n.expiry_filter === "monthly" ? "monthlies" : "all"}</td>
                  <td>{n.last_snapshot_ts ? fmtTs(n.last_snapshot_ts).slice(5, 16) : "never"}</td>
                  <td><Toggle on={n.active} label={`${n.name} active`} onChange={(v) => p.onSaveName(n.name, { active: v })} /></td>
                  <td>{job ? <span className={`pill ${job.status}`}><span className="led" />{JOB_PILL[job.status]}</span>
                    : <span className="muted">{n.active ? "—" : "inactive"}</span>}
                    {job?.error && <div className="error-text">{job.error}</div>}</td>
                  <td><EditBtn open={p.expanded === key} label={n.name} onClick={() => toggleRow(key)} /></td>
                </tr>
                {p.expanded === key && (
                  <tr className="editor-row"><td colSpan={COLS}>
                    <RegisteredEditor n={n} groups={p.groups} checkView={p.checkView} onCheck={p.onCheck}
                      onSave={async (patch) => { await p.onSaveName(n.name, patch); p.onExpand(null); }} onCancel={() => p.onExpand(null)} />
                  </td></tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RegisteredEditor({ n, groups, checkView, onCheck, onSave, onCancel }: {
  n: NameOut; groups: string[]; checkView: Props["checkView"]; onCheck: Props["onCheck"];
  onSave: (patch: NamePatch) => Promise<void>; onCancel: () => void;
}) {
  const [d, setD] = useState<NameDraft>({
    chain: n.chain_ric ?? "", display_name: n.display_name ?? "", group_name: n.group_name ?? "",
    expiry_filter: n.expiry_filter, timezone: n.timezone ?? "",
  });
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    try {
      await onSave({
        chain_ric: d.chain, display_name: d.display_name || null, group_name: d.group_name || null,
        expiry_filter: d.expiry_filter, timezone: d.timezone || null,
      });
    } finally { setSaving(false); }
  };
  return (
    <NameEditor id={`n-${n.name_id}`} value={d} groups={groups} onChange={setD}
      check={checkView(n.name, d.chain)} onCheck={() => onCheck(n.name, d.chain)}
      actions={<>
        <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="button" className="btn" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
      </>} />
  );
}

const draftOf = (r: PendingName): NameDraft => ({
  chain: r.chain, display_name: r.display_name, group_name: r.group_name, expiry_filter: r.expiry_filter, timezone: r.timezone,
});

function Toggle({ on, label, onChange }: { on: boolean; label: string; onChange: (v: boolean) => void }) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? "on" : ""}`} onClick={() => onChange(!on)} />;
}

function EditBtn({ open, label, onClick }: { open: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" className="icon-btn edit-btn" aria-expanded={open} aria-label={`Edit ${label}`} onClick={onClick}>
      {open ? "▴" : "▾"}
    </button>
  );
}
