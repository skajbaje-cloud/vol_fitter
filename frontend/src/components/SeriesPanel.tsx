import { useEffect, useState } from "react";
import { api, nearestExpiry } from "../api";
import { fmtTs } from "../lib/format";
import type { NameOut, SeriesSpec, SeriesType } from "../types";
import { SERIES_COLORS } from "./Plot";

const TYPES: { value: SeriesType; label: string }[] = [
  { value: "bidask", label: "Bid / ask" },
  { value: "mid", label: "Mid (OTM)" },
  { value: "fitted", label: "Fitted" },
];

interface RowProps {
  spec: SeriesSpec;
  color: string;
  names: NameOut[];
  focused: boolean;
  canRemove: boolean;
  onPatch: (patch: Partial<SeriesSpec>) => void;
  onRemove: () => void;
  onBaseline: () => void;
  onFocus: () => void;
}

function SeriesRow({ spec, color, names, focused, canRemove, onPatch, onRemove, onBaseline, onFocus }: RowProps) {
  const [snaps, setSnaps] = useState<string[]>([]);
  const [mats, setMats] = useState<string[]>([]);

  useEffect(() => {
    let live = true;
    api.snapshots(spec.name).then((s) => live && setSnaps(s));
    return () => { live = false; };
  }, [spec.name]);

  useEffect(() => {
    let live = true;
    api.maturities(spec.name, spec.snapshot).then((m) => live && setMats(m));
    return () => { live = false; };
  }, [spec.name, spec.snapshot]);

  // Change name/snapshot together with a valid expiry, so the chart never asks for a smile that doesn't exist.
  async function pickName(name: string) {
    const snapshot = (await api.snapshots(name))[0];
    if (!snapshot) return;
    const expiry = nearestExpiry(await api.maturities(name, snapshot), spec.expiry);
    if (expiry) onPatch({ name, snapshot, expiry });
  }
  async function pickSnapshot(snapshot: string) {
    const expiry = nearestExpiry(await api.maturities(spec.name, snapshot), spec.expiry);
    if (expiry) onPatch({ snapshot, expiry });
  }

  return (
    <div className={`series-row${focused ? " focused" : ""}`} onFocusCapture={onFocus} onClick={onFocus}>
      <span className="series-swatch" style={{ background: color }} />
      <div className="series-fields">
        <div className="series-line">
          <select aria-label="Underlying" value={spec.name} onChange={(e) => pickName(e.target.value)}>
            {names.map((n) => <option key={n.name} value={n.name}>{n.name}</option>)}
          </select>
          <select aria-label="Expiry" value={spec.expiry} onChange={(e) => onPatch({ expiry: e.target.value })}>
            {(mats.length ? mats : [spec.expiry]).map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div className="series-line">
          <select aria-label="Snapshot" value={spec.snapshot} onChange={(e) => pickSnapshot(e.target.value)}>
            {(snaps.length ? snaps : [spec.snapshot]).map((s) => <option key={s} value={s}>{fmtTs(s)}</option>)}
          </select>
        </div>
        <div className="series-line series-meta">
          <select aria-label="Show as" value={spec.type} onChange={(e) => onPatch({ type: e.target.value as SeriesType })}>
            {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <button type="button" className={`chip${spec.baseline ? " active" : ""}`} onClick={onBaseline}
            title="Difference mode subtracts this series from every other one">
            baseline
          </button>
          <span className="mono muted">#{spec.id}</span>
        </div>
      </div>
      <button type="button" className="icon-btn" onClick={onRemove} disabled={!canRemove} title="Remove series" aria-label="Remove series">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
      </button>
    </div>
  );
}

interface Props {
  series: SeriesSpec[];
  names: NameOut[];
  focusedId: number | null;
  onChange: (updater: (prev: SeriesSpec[]) => SeriesSpec[]) => void;
  onFocus: (id: number) => void;
  onAdd: () => void;
}

export function SeriesPanel({ series, names, focusedId, onChange, onFocus, onAdd }: Props) {
  const patch = (id: number, p: Partial<SeriesSpec>) => onChange((prev) => prev.map((s) => (s.id === id ? { ...s, ...p } : s)));
  const remove = (id: number) =>
    onChange((prev) => {
      const next = prev.filter((s) => s.id !== id);
      return next.some((s) => s.baseline) ? next : next.map((s, i) => ({ ...s, baseline: i === 0 }));
    });
  const setBaseline = (id: number) => onChange((prev) => prev.map((s) => ({ ...s, baseline: s.id === id })));

  return (
    <div className="panel">
      <div className="panel-head">Series</div>
      <div className="panel-body">
        {series.map((s, idx) => (
          <SeriesRow key={s.id} spec={s} color={SERIES_COLORS[idx % SERIES_COLORS.length]} names={names}
            focused={s.id === focusedId} canRemove={series.length > 1}
            onPatch={(p) => patch(s.id, p)} onRemove={() => remove(s.id)}
            onBaseline={() => setBaseline(s.id)} onFocus={() => onFocus(s.id)} />
        ))}
        <button type="button" className="add-series" onClick={onAdd}>+ Add series</button>
      </div>
    </div>
  );
}
