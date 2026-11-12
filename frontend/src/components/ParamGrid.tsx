import { useMemo } from "react";
import { fmtTs } from "../lib/format";
import {
  MARGIN, MAX_OVERLAY, OVERLAY_PX, ROW_GAP_PX, ROW_PX, buildFigure, type GridOptions, type RowFits,
} from "../lib/paramGrid";
import type { SeriesSpec } from "../types";
import { Plot, SERIES_COLORS } from "./Plot";

interface Props {
  rows: RowFits[];
  opts: GridOptions;
  snapshotsFor: (name: string) => string[];
  onSnapshot: (id: number, snapshot: string) => void;
  onRemove: (id: number) => void;
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

/** Row labels (name, snapshot picker, remove) beside one Plotly figure of parameter vs T. */
export function ParamGrid({ rows, opts, snapshotsFor, onSnapshot, onRemove, onOpenInPlots }: Props) {
  const fig = useMemo(() => buildFigure(rows, opts), [rows, opts]);
  const overlay = opts.view === "overlay";
  const shown = overlay ? rows.slice(0, MAX_OVERLAY) : rows;

  const open = (cd: unknown) => {
    const [name, snapshot, expiry] = cd as string[];
    if (name && snapshot && expiry) onOpenInPlots({ name, snapshot, expiry, type: "fitted" });
  };

  return (
    <div className="pgrid">
      <div className="pgrid-labels" style={{ paddingTop: MARGIN.t }}>
        {shown.map((r, i) => {
          const n = r.fits?.filter((f) => f.fit_status).length ?? 0;
          return (
            <div key={r.row.id} className="pgrid-label"
              style={overlay ? undefined : { height: ROW_PX, paddingBottom: ROW_GAP_PX }}>
              <div className="pgrid-name">
                {overlay && <i className="swatch" style={{ background: SERIES_COLORS[i] }} />}
                <span className="mono">{r.row.name}</span>
                <button type="button" className="icon-btn" aria-label={`Remove ${r.row.name}`} onClick={() => onRemove(r.row.id)}>×</button>
              </div>
              <select aria-label={`Snapshot for ${r.row.name}`} value={r.row.snapshot} onChange={(e) => onSnapshot(r.row.id, e.target.value)}>
                {snapshotsFor(r.row.name).map((s) => <option key={s} value={s}>{fmtTs(s).slice(0, 16)}</option>)}
              </select>
              <span className="muted">{r.fits === null ? "loading…" : `${n} fitted expir${n === 1 ? "y" : "ies"}`}</span>
            </div>
          );
        })}
        {overlay && rows.length > MAX_OVERLAY && (
          <div className="muted pgrid-more">{rows.length - MAX_OVERLAY} more row{rows.length - MAX_OVERLAY === 1 ? "" : "s"} not drawn: overlay shows the first {MAX_OVERLAY}.</div>
        )}
      </div>
      <div className="pgrid-plot" style={{ minHeight: overlay ? OVERLAY_PX : undefined }}>
        <Plot data={fig.data} layout={fig.layout} height={fig.height} onPointClick={open} />
      </div>
    </div>
  );
}
