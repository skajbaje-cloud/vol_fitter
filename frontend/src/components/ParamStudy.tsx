import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { ParamGrid } from "./ParamGrid";
import { Seg } from "./Seg";
import {
  defaultRows, fittedSnapshots, type GridOptions, type GridView, type ParamRow, type RowFits, type XScale, type YScale,
} from "../lib/paramGrid";
import type { ExpiryFit, FitCoverage, NameOut, SeriesSpec } from "../types";

interface Props {
  names: NameOut[];
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

const key = (r: ParamRow) => `${r.name}|${r.snapshot}`;

/** Fitted smile parameters against T: one row per name+snapshot, one column per parameter. */
export function ParamStudy({ names, onOpenInPlots }: Props) {
  const [coverage, setCoverage] = useState<FitCoverage[] | null>(null);
  const [rows, setRows] = useState<ParamRow[] | null>(null);
  const [fits, setFits] = useState<Map<string, ExpiryFit[]>>(new Map());
  const [view, setView] = useState<GridView>("grid");
  const [x, setX] = useState<XScale>("T");
  const [y, setY] = useState<YScale>("shared");
  const [error, setError] = useState("");
  const nextId = useRef(1000);
  const asked = useRef(new Set<string>());

  const order = useMemo(() => names.map((n) => n.name), [names]);
  const load = useCallback(() => {
    setError("");
    asked.current.clear();
    setFits(new Map());
    return api.fitCoverage().then((c) => {
      setCoverage(c);
      setRows((prev) => prev ?? defaultRows(c, order));
    }, (e: Error) => setError(e.message));
  }, [order]);
  useEffect(() => { load(); }, []);                // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch each row's per-expiry fits once; rows sharing a name+snapshot share the request.
  useEffect(() => {
    for (const r of rows ?? []) {
      const k = key(r);
      if (asked.current.has(k)) continue;
      asked.current.add(k);
      api.expiryFits(r.name, r.snapshot).then(
        (f) => setFits((m) => new Map(m).set(k, f)),
        (e: Error) => setError(`${r.name}: ${e.message}`),
      );
    }
  }, [rows, fits]);

  const snapshotsFor = useCallback((name: string) => fittedSnapshots(coverage ?? [], name), [coverage]);
  const fittedNames = order.filter((n) => snapshotsFor(n).length > 0);
  const rowFits: RowFits[] = useMemo(() => (rows ?? []).map((row) => ({ row, fits: fits.get(key(row)) ?? null })), [rows, fits]);
  const opts: GridOptions = useMemo(() => ({ view, x, y }), [view, x, y]);

  const add = (name: string) => {
    const snapshot = snapshotsFor(name)[0];
    if (snapshot) setRows((r) => [...(r ?? []), { id: nextId.current++, name, snapshot }]);
  };
  const setSnapshot = (id: number, snapshot: string) => setRows((r) => (r ?? []).map((x) => (x.id === id ? { ...x, snapshot } : x)));
  const remove = (id: number) => setRows((r) => (r ?? []).filter((x) => x.id !== id));

  return (
    <>
      <div className="toolbar">
        <label className="field"><span className="field-label">Add a row</span>
          <select value="" onChange={(e) => e.target.value && add(e.target.value)}>
            <option value="">+ Add name…</option>
            {fittedNames.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <div className="field"><span className="field-label">View</span>
          <Seg label="View" value={view} onChange={setView} options={[
            { value: "grid", label: "Grid" }, { value: "overlay", label: "Overlay" }]} />
        </div>
        <div className="field"><span className="field-label">Y scale</span>
          <Seg label="Y scale" value={y} onChange={setY} options={[
            { value: "shared", label: "Shared per column" }, { value: "own", label: "Own per cell" }]} />
        </div>
        <div className="field"><span className="field-label">X axis</span>
          <Seg label="X axis" value={x} onChange={setX} options={[{ value: "T", label: "T" }, { value: "sqrtT", label: "√T" }]} />
        </div>
        <div className="field"><span className="field-label">Rows</span>
          <div className="pgrid-actions">
            <button type="button" className="btn-secondary btn-xs" onClick={() => coverage && setRows(defaultRows(coverage, order))}>Reset</button>
            <button type="button" className="btn-secondary btn-xs" onClick={() => setRows([])}>Clear</button>
            <button type="button" className="btn-secondary btn-xs" onClick={load} title="Re-read fits (after a refit on the Fits tab)">Refresh</button>
          </div>
        </div>
        {error && <span className="error-text toolbar-hint">{error}</span>}
      </div>
      <div className="panel">
        {rows === null ? <div className="muted empty">Loading…</div>
          : rows.length === 0 ? <div className="muted empty">
            {fittedNames.length ? "No rows. Add a name above, or press Reset." : "No fits yet. Run some from the Fits tab."}</div>
          : <ParamGrid rows={rowFits} opts={opts} snapshotsFor={snapshotsFor}
              onSnapshot={setSnapshot} onRemove={remove} onOpenInPlots={onOpenInPlots} />}
      </div>
      <div className="note">
        Raw fitted parameters, not normalised. Hollow points are expiries whose fit failed or missed the quotes.
        Hover a point for its expiry; click it to open that smile in Plots.
      </div>
    </>
  );
}
