import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtTs } from "../lib/format";
import type { NameOut } from "../types";

interface Row { name: string; snapshot: string; expiries: number }

export function FitsPage({ names }: { names: NameOut[] }) {
  const [rows, setRows] = useState<Row[] | null>(null);

  // Nothing is fitted yet (Phase 2), so every priced snapshot is awaiting a fit.
  useEffect(() => {
    Promise.all(names.map(async (n) => {
      const snaps = await api.snapshots(n.name);
      return Promise.all(snaps.map(async (s) => ({ name: n.name, snapshot: s, expiries: (await api.maturities(n.name, s)).length })));
    })).then((r) => setRows(r.flat()), () => setRows([]));
  }, [names]);

  return (
    <>
      <div className="phase-banner">Per-expiry smile fitting (Phase 2) isn't built yet. This page lists what's waiting for it; the controls are disabled.</div>
      <div className="toolbar dimmed" aria-disabled="true">
        <div className="field"><span className="field-label">Scope</span>
          <div className="seg"><button type="button" className="active" disabled>Single underlying</button><button type="button" disabled>All active names</button></div>
        </div>
        <div className="spacer" />
        <button type="button" className="btn" disabled>Run fit</button>
      </div>
      <div className="panel">
        <div className="panel-head">Snapshots awaiting a fit</div>
        {rows === null ? <div className="muted empty">Loading…</div> : rows.length === 0 ? (
          <div className="muted empty">No priced snapshots yet. Run one from the Snapshot page.</div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Name</th><th>Snapshot</th><th>Expiries</th><th>Status</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.name + r.snapshot}>
                    <td className="name">{r.name}</td><td>{fmtTs(r.snapshot)}</td><td>{r.expiries}</td>
                    <td><span className="pill queued"><span className="led" />not fitted</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
