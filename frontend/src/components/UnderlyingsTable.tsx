import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { fmtPct, fmtTs } from "../lib/format";
import { type PendingName, nameKey, pendingKey, pendingState } from "../lib/names";
import { type Draft, fromRow, sameDraft, validate, WEEKDAYS } from "../lib/schedule";
import { hhmmIn, todayIn, tzAbbr, wallToInstant } from "../lib/tz";
import { DAYS, type FitCoverage, type JobOut, type NameOut, type NamePatch, type ScheduleRow, type SeriesSpec } from "../types";
import { BulkTimesRow } from "./BulkTimesRow";
import { CoveragePill, FitDetail } from "./FitDetail";
import { type CheckView, type NameDraft, NameEditor } from "./NameEditor";
import { TimeInput } from "./TimeInput";

export interface TableProps {
  pending: PendingName[];
  names: NameOut[];
  coverage: Map<string, FitCoverage[]>;        // name -> its snapshots, newest first
  schedule: Map<string, ScheduleRow>;
  drafts: Record<string, Draft>;
  selected: Set<string>;
  selectable: string[];
  expanded: string | null;
  groups: string[];
  version: number;                              // bumps when fits finish
  bulk: { selected: ScheduleRow[]; onApply: Parameters<typeof BulkTimesRow>[0]["onApply"] } | null;
  lastJob: (name: string, kind: JobOut["kind"]) => JobOut | undefined;
  checkView: (name: string, chain: string) => CheckView | null;
  onToggle: (key: string) => void;
  onToggleAll: () => void;
  onExpand: (key: string | null) => void;
  onPendingChange: (ric: string, patch: Partial<PendingName>) => void;
  onRemovePending: (ric: string) => void;
  onRegister: (row: PendingName) => void;
  onSaveName: (name: string, patch: NamePatch) => Promise<void>;
  onCheck: (name: string, chain: string) => void;
  onDraft: (name: string, d: Draft) => void;
  onSnapshot: (name: string) => void;
  onFit: (name: string) => void;
  onFitSnapshot: (name: string, snapshot: string) => void;
  onDelete: (name: string) => void;
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

const STATE_PILL = {
  looking: ["running", "looking up"], notfound: ["failed", "not found"], choose: ["warn", "choose chain"], ready: ["done", "ready"],
} as const;
const COLS = 9, TIMES_COL = 4;              // the snap-times column sits after sel, name, on, last snap
const live = (j?: JobOut) => !!j && (j.status === "queued" || j.status === "running");
const short = (ts: string | null | undefined) => (ts ? fmtTs(ts).slice(5, 16) : null);

/** A job that's still going, or failed last time, says so; otherwise the cell shows its normal value. */
function JobOr({ job, verb, children }: { job?: JobOut; verb: string; children: ReactNode }) {
  if (live(job)) return <span className={`pill ${job!.status}`}><span className="led" />{job!.status === "queued" ? "queued" : verb}</span>;
  if (job?.status === "failed") return <span className="pill failed" title={job.error ?? ""}><span className="led" />failed</span>;
  return <>{children}</>;
}

const daysLabel = (d: Draft) => (d.days.length === 7 ? "daily" : d.days.join() === WEEKDAYS.join() ? "Mon–Fri" : d.days.join(" ") || "no days");

/** Up to five snap times, typed straight into the row (local to the name's zone); days and on/off live under ▾. */
function TimesCell({ name, r, d, onChange }: { name: string; r?: ScheduleRow; d?: Draft; onChange: (d: Draft) => void }) {
  if (!r || !d) return <span className="muted">—</span>;
  const zone = r.timezone;
  if (!zone) return <span className="muted" title="Set a time zone under ▾ to schedule snaps">no time zone</span>;
  const server = fromRow(r);
  const { errors, warnings } = validate(d);
  const abbr = tzAbbr(zone);
  const userTime = (t: string) => (/^\d\d:\d\d$/.test(t) ? `${hhmmIn(wallToInstant(zone, todayIn(zone), t))} your time` : "");
  return (
    <>
      <div className="times-cell">
        {d.times.map((t, i) => (
          <TimeInput key={i} value={t} changed={t !== server.times[i]} title={userTime(t)} label={`${name} time ${i + 1} (${abbr})`}
            onChange={(v) => onChange({ ...d, times: d.times.map((x, j) => (j === i ? v : x)) })} />
        ))}
      </div>
      <div className={`job-sub ${d.enabled ? "muted" : "warn-text"}`}>
        {abbr} · {daysLabel(d)}{d.enabled ? "" : " · schedule off"}{sameDraft(d, server) ? "" : " · unsaved"}
      </div>
      {errors.map((e) => <div key={e} className="error-text">{e}.</div>)}
      {warnings.map((w) => <div key={w} className="warn-text job-sub">{w}.</div>)}
    </>
  );
}

export function UnderlyingsTable(p: TableProps) {
  const all = useRef<HTMLInputElement>(null);
  const nSel = p.selectable.filter((k) => p.selected.has(k)).length;
  useEffect(() => { if (all.current) all.current.indeterminate = nSel > 0 && nSel < p.selectable.length; }, [nSel, p.selectable.length]);
  const toggle = (key: string) => p.onExpand(p.expanded === key ? null : key);

  return (
    <div className="table-scroll">
      <table className="data-table names-table">
        <thead>
          <tr>
            <th className="sel"><input ref={all} type="checkbox" aria-label="Select all"
              checked={p.selectable.length > 0 && nSel === p.selectable.length} onChange={p.onToggleAll} /></th>
            <th>Name</th><th>On</th><th>Last snap</th><th>Snap times</th><th>Latest fit</th><th>Inside</th><th>Unfitted</th><th />
          </tr>
        </thead>
        <tbody>
          {p.bulk && p.bulk.selected.length > 0 && (
            <BulkTimesRow selected={p.bulk.selected} rows={[...p.schedule.values()]} drafts={p.drafts}
              lead={TIMES_COL} tail={COLS - TIMES_COL - 1} onApply={p.bulk.onApply} />
          )}
          {p.pending.map((row) => {
            const key = pendingKey(row.ric), st = pendingState(row), [cls, label] = STATE_PILL[st];
            const open = p.expanded === key && !!row.lookup?.found;
            return (
              <Fragment key={key}>
                <tr className={open ? "open" : ""}>
                  <td className="sel"><input type="checkbox" aria-label={`Select ${row.ric}`} disabled={st !== "ready"}
                    checked={p.selected.has(key)} onChange={() => p.onToggle(key)} /></td>
                  <td className="name">{row.ric}<div className="muted job-sub">{row.display_name || "new"}</div></td>
                  <td><Toggle on={row.active} label={`${row.ric} active`} onChange={(v) => p.onPendingChange(row.ric, { active: v })} /></td>
                  <td colSpan={COLS - 4}>
                    <span className={`pill ${cls}`}><span className="led" />{label}</span>
                    {(row.lookupError || row.lookup?.error) && <div className="error-text">{row.lookupError || row.lookup?.error}</div>}
                  </td>
                  <td><div className="row-actions">
                    {row.lookup?.found && <ExpandBtn open={open} label={row.ric} onClick={() => toggle(key)} />}
                    <IconBtn label={`Remove ${row.ric}`} onClick={() => p.onRemovePending(row.ric)} />
                  </div></td>
                </tr>
                {open && (
                  <tr className="editor-row"><td colSpan={COLS}>
                    <NameEditor id={key} value={draftOf(row)} candidates={row.lookup!.candidates} groups={p.groups}
                      check={p.checkView(row.ric, row.chain)} onCheck={() => p.onCheck(row.ric, row.chain)}
                      onChange={(d) => p.onPendingChange(row.ric, { ...d })}
                      actions={<button type="button" className="btn" disabled={st !== "ready"} onClick={() => p.onRegister(row)}>Register</button>} />
                  </td></tr>
                )}
              </Fragment>
            );
          })}
          {p.names.map((n) => {
            const key = nameKey(n.name), open = p.expanded === key;
            const snaps = p.coverage.get(n.name) ?? [], latest = snaps[0];
            const unfitted = snaps.filter((c) => c.n_fitted === 0).length;
            const snapJob = p.lastJob(n.name, "snapshot"), fitJob = p.lastJob(n.name, "fit");
            return (
              <Fragment key={key}>
                <tr className={`${open ? "open" : ""} ${n.active ? "" : "inactive"}`}>
                  <td className="sel"><input type="checkbox" aria-label={`Select ${n.name}`} checked={p.selected.has(key)} onChange={() => p.onToggle(key)} /></td>
                  <td className="name">{n.name}{n.display_name && <div className="muted job-sub dname" title={n.display_name}>{n.display_name}</div>}</td>
                  <td><Toggle on={n.active} label={`${n.name} active`} onChange={(v) => p.onSaveName(n.name, { active: v })} /></td>
                  <td><JobOr job={snapJob} verb="snapping">{short(n.last_snapshot_ts) ?? <span className="muted">never</span>}</JobOr></td>
                  <td><TimesCell name={n.name} r={p.schedule.get(n.name)} d={p.drafts[n.name]} onChange={(d) => p.onDraft(n.name, d)} /></td>
                  <td><JobOr job={fitJob} verb="fitting">{latest ? <CoveragePill c={latest} /> : <span className="muted">—</span>}</JobOr></td>
                  <td>{fmtPct(latest?.mean_pct_inside, 0)}</td>
                  <td>{unfitted ? `${unfitted} of ${snaps.length}` : <span className="muted">—</span>}</td>
                  <td><div className="row-actions">
                    <button type="button" className="btn-secondary btn-xs" disabled={live(snapJob)} onClick={() => p.onSnapshot(n.name)}>Snap</button>
                    <button type="button" className="btn-secondary btn-xs" disabled={live(fitJob) || !unfitted}
                      title={unfitted ? "Fit every snapshot not fitted yet" : "Nothing unfitted; refit a snapshot from ▾"}
                      onClick={() => p.onFit(n.name)}>Fit</button>
                    <ExpandBtn open={open} label={n.name} onClick={() => toggle(key)} />
                    <IconBtn label={`Delete ${n.name}`} onClick={() => p.onDelete(n.name)} trash />
                  </div></td>
                </tr>
                {open && (
                  <tr className="editor-row"><td colSpan={COLS}>
                    <RegisteredEditor n={n} groups={p.groups} checkView={p.checkView} onCheck={p.onCheck}
                      onSave={(patch) => p.onSaveName(n.name, patch)} />
                    {p.schedule.get(n.name) && p.drafts[n.name] && (
                      <ScheduleEditor r={p.schedule.get(n.name)!} d={p.drafts[n.name]} onChange={(d) => p.onDraft(n.name, d)} />
                    )}
                    {snaps.length > 0 && (
                      <FitDetail name={n.name} snapshots={snaps} busy={live(fitJob)} version={p.version}
                        onFitSnapshot={(s) => p.onFitSnapshot(n.name, s)} onOpenInPlots={p.onOpenInPlots} />
                    )}
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

function RegisteredEditor({ n, groups, checkView, onCheck, onSave }: {
  n: NameOut; groups: string[]; checkView: TableProps["checkView"]; onCheck: TableProps["onCheck"];
  onSave: (patch: NamePatch) => Promise<void>;
}) {
  const initial: NameDraft = {
    chain: n.chain_ric ?? "", display_name: n.display_name ?? "", group_name: n.group_name ?? "",
    expiry_filter: n.expiry_filter, timezone: n.timezone ?? "",
  };
  const [d, setD] = useState<NameDraft>(initial);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(d) !== JSON.stringify(initial);
  const save = async () => {
    setSaving(true);
    try {
      await onSave({
        chain_ric: d.chain, display_name: d.display_name || null, group_name: d.group_name || null,
        expiry_filter: d.expiry_filter, timezone: d.timezone || null,
      });
    } catch { /* the page shows the error */ } finally { setSaving(false); }
  };
  return (
    <NameEditor id={`n-${n.name_id}`} value={d} groups={groups} onChange={setD}
      check={checkView(n.name, d.chain)} onCheck={() => onCheck(n.name, d.chain)}
      actions={<button type="button" className="btn" onClick={save} disabled={saving || !dirty}>{saving ? "Saving…" : "Save details"}</button>} />
  );
}

/** Which days a name's snap times fire on, and an on/off switch; saved with the page's "Save schedule". */
function ScheduleEditor({ r, d, onChange }: { r: ScheduleRow; d: Draft; onChange: (d: Draft) => void }) {
  const zone = r.timezone;
  const toggleDay = (day: (typeof DAYS)[number]) =>
    onChange({ ...d, days: d.days.includes(day) ? d.days.filter((x) => x !== day) : DAYS.filter((x) => x === day || d.days.includes(x)) });

  return (
    <div className="sched-edit">
      <span className="field-label">Schedule days{zone ? ` · times are ${zone} wall-clock` : ""}</span>
      {!zone ? <span className="muted">Set a time zone above first.</span> : (
        <>
          <div className="sched-days" role="group" aria-label={`${r.name} schedule days`}>
            {DAYS.map((day) => (
              <button key={day} type="button" aria-pressed={d.days.includes(day)} className={d.days.includes(day) ? "active" : ""}
                onClick={() => toggleDay(day)}>{day}</button>
            ))}
            <span className="sched-gap" />
            <Toggle on={d.enabled} label={`${r.name} schedule on`} onChange={(v) => onChange({ ...d, enabled: v })} />
            <span className="muted">{d.enabled ? "schedule on" : "schedule off"}</span>
          </div>
        </>
      )}
    </div>
  );
}

const draftOf = (r: PendingName): NameDraft => ({
  chain: r.chain, display_name: r.display_name, group_name: r.group_name, expiry_filter: r.expiry_filter, timezone: r.timezone,
});

function Toggle({ on, label, onChange }: { on: boolean; label: string; onChange: (v: boolean) => void }) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? "on" : ""}`} onClick={() => onChange(!on)} />;
}

function ExpandBtn({ open, label, onClick }: { open: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" className="icon-btn edit-btn" aria-expanded={open} aria-label={`Details for ${label}`} title="Details, schedule, fits" onClick={onClick}>
      {open ? "▴" : "▾"}
    </button>
  );
}

function IconBtn({ label, onClick, trash }: { label: string; onClick: () => void; trash?: boolean }) {
  return (
    <button type="button" className="icon-btn" aria-label={label} title={label} onClick={onClick}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d={trash ? "M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3" : "M18 6L6 18M6 6l12 12"} />
      </svg>
    </button>
  );
}
