import type { ReactNode } from "react";
import { CHAIN_RE } from "../lib/names";
import { allZones, offsetLabel, tzAbbr } from "../lib/tz";
import type { ChainCandidate, ExpiryFilter } from "../types";
import { Seg } from "./Seg";

export interface NameDraft { chain: string; display_name: string; group_name: string; expiry_filter: ExpiryFilter; timezone: string }

export interface CheckView { busy: boolean; text: string; warn?: boolean }

interface Props {
  id: string;
  value: NameDraft;
  candidates?: ChainCandidate[];
  groups: string[];
  check: CheckView | null;
  onChange: (d: NameDraft) => void;
  onCheck: () => void;
  actions: ReactNode;
}

const EXPIRY_OPTIONS = [
  { value: "all" as const, label: "All listed" },
  { value: "monthly" as const, label: "Monthlies only" },
];

/** Inline editor shown under a row: which chain, what to call it, which group, which expiries. */
export function NameEditor({ id, value, candidates, groups, check, onChange, onCheck, actions }: Props) {
  const set = (patch: Partial<NameDraft>) => onChange({ ...value, ...patch });
  const listed = candidates?.some((c) => c.chain_ric === value.chain) ?? false;
  const chainOk = CHAIN_RE.test(value.chain);
  const zoneOk = !value.timezone || allZones().includes(value.timezone);
  const zoneHint = !value.timezone ? "Needed for scheduled snaps" : zoneOk ? `${tzAbbr(value.timezone)} · ${offsetLabel(value.timezone)} now` : "Not a known time zone";

  return (
    <div className="name-editor">
      <fieldset className="ne-chains">
        <legend className="field-label">Chain RIC</legend>
        {candidates?.map((c) => (
          <label key={c.chain_ric} className="ne-cand">
            <input type="radio" name={`${id}-chain`} checked={value.chain === c.chain_ric} onChange={() => set({ chain: c.chain_ric })} />
            <span className="mono">{c.chain_ric}</span>
            {c.preferred && <span className="tag">best match</span>}
            <span className="muted ne-title">{c.title}</span>
          </label>
        ))}
        <label className="ne-cand">
          {!!candidates?.length && <input type="radio" name={`${id}-chain`} checked={!listed} onChange={() => set({ chain: "" })} />}
          <input className="ne-custom" value={listed ? "" : value.chain} placeholder="0#ROOT*.U"
            aria-label="Chain RIC" onChange={(e) => set({ chain: e.target.value.trim() })} />
        </label>
        <div className="ne-check">
          <button type="button" className="btn-secondary" onClick={onCheck} disabled={!chainOk || check?.busy}>
            {check?.busy ? "Checking…" : "Check chain"}
          </button>
          <span className={check?.warn ? "warn-text" : "muted"}>
            {check?.text ?? "Expands the chain and counts its options. Large chains take a few minutes."}
          </span>
        </div>
      </fieldset>
      <div className="ne-fields">
        <label className="field"><span className="field-label">Display name</span>
          <input value={value.display_name} onChange={(e) => set({ display_name: e.target.value })} /></label>
        <label className="field"><span className="field-label">Group</span>
          <input value={value.group_name} list={`${id}-groups`} placeholder="US single"
            onChange={(e) => set({ group_name: e.target.value })} />
          <datalist id={`${id}-groups`}>{groups.map((g) => <option key={g} value={g} />)}</datalist></label>
        <label className="field"><span className="field-label">Time zone</span>
          <input value={value.timezone} list={`${id}-zones`} placeholder="America/New_York"
            onChange={(e) => set({ timezone: e.target.value.trim() })} />
          <datalist id={`${id}-zones`}>{allZones().map((z) => <option key={z} value={z} />)}</datalist>
          <span className={zoneOk ? "muted" : "warn-text"}>{zoneHint}</span></label>
        <div className="field"><span className="field-label">Expiries</span>
          <Seg label="Expiries" value={value.expiry_filter} options={EXPIRY_OPTIONS} onChange={(v) => set({ expiry_filter: v })} /></div>
        <div className="ne-actions">{actions}</div>
      </div>
    </div>
  );
}
