import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtTs } from "../lib/format";
import type { NameOut } from "../types";
import { StepSelect } from "./StepSelect";

export interface Picker {
  name: string;
  setName: (n: string) => void;
  snaps: string[];
  snapshot: string;
  setSnapshot: (s: string) => void;
}

/** Underlying + snapshot selection shared by Grid, Smile lab and Curvature. Re-reads snapshots after a new one lands. */
export function useNameSnapshot(names: NameOut[]): Picker {
  const [name, setName] = useState(names[0]?.name ?? "");
  const [snaps, setSnaps] = useState<string[]>([]);
  const [snap, setSnap] = useState({ name: "", ts: "" });      // the snapshot remembers which name it belongs to
  const last = names.find((n) => n.name === name)?.last_snapshot_ts;

  useEffect(() => {
    if (names.length && !names.some((n) => n.name === name)) setName(names[0].name);   // e.g. the name was deleted
  }, [names, name]);

  useEffect(() => {
    if (!name) return;
    let live = true;
    api.snapshots(name).then((s) => {
      if (!live) return;
      setSnaps(s);
      setSnap((prev) => ({ name, ts: s.includes(prev.ts) ? prev.ts : s[0] ?? "" }));
    });
    return () => { live = false; };
  }, [name, last]);

  // Until the new name's snapshots arrive, report none, so callers never ask for (new name, old snapshot).
  const snapshot = snap.name === name ? snap.ts : "";
  return { name, setName, snaps: snapshot ? snaps : [], snapshot, setSnapshot: (ts) => setSnap({ name, ts }) };
}

/** step: ‹ › buttons beside the snapshot, to walk through them one at a time. */
export function NameSnapshotFields({ picker, names, step }: { picker: Picker; names: NameOut[]; step?: boolean }) {
  return (
    <>
      <label className="field"><span className="field-label">Underlying</span>
        <select value={picker.name} onChange={(e) => picker.setName(e.target.value)}>
          {names.map((n) => <option key={n.name}>{n.name}</option>)}
        </select>
      </label>
      {step ? (
        <div className="field"><span className="field-label">Snapshot</span>
          <StepSelect label="snapshot" value={picker.snapshot} onChange={picker.setSnapshot} newestFirst
            options={picker.snaps.map((s) => ({ value: s, label: fmtTs(s) }))} />
        </div>
      ) : (
        <label className="field"><span className="field-label">Snapshot</span>
          <select value={picker.snapshot} onChange={(e) => picker.setSnapshot(e.target.value)}>
            {picker.snaps.map((s) => <option key={s} value={s}>{fmtTs(s)}</option>)}
          </select>
        </label>
      )}
    </>
  );
}
