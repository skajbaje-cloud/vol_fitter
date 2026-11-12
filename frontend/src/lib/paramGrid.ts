/** Shapes per-expiry fits into one Plotly figure: parameter (columns) against T, one row per name+snapshot. */
import { SERIES_COLORS, axis } from "../components/Plot";
import { fmtTs } from "./format";
import type { ExpiryFit, FitCoverage } from "../types";

export type ParamKey = "sigma_atm" | "skew" | "kappa_put" | "kappa_call";
export type XScale = "T" | "sqrtT";
export type YScale = "shared" | "own";
export type GridView = "grid" | "overlay";

export interface ParamRow { id: number; name: string; snapshot: string }
export interface RowFits { row: ParamRow; fits: ExpiryFit[] | null }   // null while loading
export interface GridOptions { view: GridView; x: XScale; y: YScale }

export const PARAMS: { key: ParamKey; label: string; tick: string; hover: string }[] = [
  { key: "sigma_atm", label: "σ atm", tick: ".0%", hover: ".2%" },
  { key: "skew", label: "skew", tick: ".3~f", hover: ".4f" },
  { key: "kappa_put", label: "κ put", tick: ".3~f", hover: ".4f" },
  { key: "kappa_call", label: "κ call", tick: ".3~f", hover: ".4f" },
];
export const ROW_PX = 150;          // one grid row, in pixels (the row labels beside the chart use the same height)
export const OVERLAY_PX = 340;
export const MAX_OVERLAY = SERIES_COLORS.length;
export const MARGIN = { t: 26, b: 22, l: 52, r: 10 };
export const ROW_GAP_PX = 30;       // space under each row for its T tick labels
const COL_GAP = 0.055;

/** Snapshots of `name` that have at least one fitted expiry, newest first. */
export function fittedSnapshots(coverage: FitCoverage[], name: string): string[] {
  return coverage.filter((c) => c.name === name && c.n_fitted > 0).map((c) => c.snapshot_ts).sort().reverse();
}

/** One row per name (in `names` order) on its latest fitted snapshot. */
export function defaultRows(coverage: FitCoverage[], names: string[]): ParamRow[] {
  return names.flatMap((name, i) => {
    const s = fittedSnapshots(coverage, name)[0];
    return s ? [{ id: i + 1, name, snapshot: s }] : [];
  });
}

const colDomain = (c: number) => [c / PARAMS.length + (c ? COL_GAP : 0), (c + 1) / PARAMS.length - 0.008];
const isWeak = (f: ExpiryFit) => f.fit_status !== "ok" || f.smile_quality_flag === "miss";

function trace(r: RowFits, p: (typeof PARAMS)[number], opts: GridOptions, ax: number, color: string) {
  const pts = (r.fits ?? []).filter((f) => f.T != null && f[p.key] != null).sort((a, b) => a.T! - b.T!);
  const id = ax === 1 ? "" : String(ax);
  return {
    type: "scatter", mode: "lines+markers", xaxis: `x${id}`, yaxis: `y${id}`, showlegend: false,
    x: pts.map((f) => (opts.x === "sqrtT" ? Math.sqrt(f.T!) : f.T!)), y: pts.map((f) => f[p.key]),
    customdata: pts.map((f) => [r.row.name, r.row.snapshot, f.expiry_date, f.T, f.fit_status ?? "", f.smile_quality_flag === "miss" ? " · miss" : ""]),
    line: { color, width: 1.5 },
    marker: { color, size: 5.5, symbol: pts.map((f) => (isWeak(f) ? "circle-open" : "circle")), line: { color, width: 1.5 } },
    hovertemplate: `%{customdata[2]} · T %{customdata[3]:.3f}<br>${p.label} %{y:${p.hover}}<br>%{customdata[4]}%{customdata[5]}`
      + `<extra>${r.row.name} ${fmtTs(r.row.snapshot).slice(5, 16)}</extra>`,
  };
}

/** The whole figure; `height` matches the row labels drawn next to it in grid view. */
export function buildFigure(rows: RowFits[], opts: GridOptions) {
  const shown = opts.view === "overlay" ? rows.slice(0, MAX_OVERLAY) : rows;
  const nRows = opts.view === "overlay" ? 1 : shown.length;
  const height = MARGIN.t + MARGIN.b + (opts.view === "overlay" ? OVERLAY_PX : nRows * ROW_PX);
  const plotH = height - MARGIN.t - MARGIN.b;
  const gap = ROW_GAP_PX / plotH;
  const layout: Record<string, unknown> = { margin: MARGIN, showlegend: false, annotations: [] as unknown[] };
  const data: unknown[] = [];

  for (let r = 0; r < nRows; r++) {
    const top = 1 - r / nRows, bottom = 1 - (r + 1) / nRows;
    PARAMS.forEach((p, c) => {
      const ax = r * PARAMS.length + c + 1;
      const id = ax === 1 ? "" : String(ax);
      const [x0, x1] = colDomain(c);
      layout[`xaxis${id}`] = axis({ domain: [x0, x1], anchor: `y${id}`, matches: ax === 1 ? undefined : "x",
        title: r === nRows - 1 ? { text: opts.x === "sqrtT" ? "√T" : "T (years)", standoff: 4 } : undefined });
      layout[`yaxis${id}`] = axis({ domain: [bottom + gap, top], anchor: `x${id}`, tickformat: p.tick,
        matches: opts.y === "shared" && r > 0 ? `y${c === 0 ? "" : c + 1}` : undefined });
      const group = opts.view === "overlay" ? shown : [shown[r]];
      group.forEach((row, i) => data.push(trace(row, p, opts, ax, SERIES_COLORS[opts.view === "overlay" ? i : 0])));
    });
  }
  layout.annotations = PARAMS.map((p, c) => ({
    text: p.label, xref: "paper", yref: "paper", x: (colDomain(c)[0] + colDomain(c)[1]) / 2, y: 1,
    yanchor: "bottom", showarrow: false, font: { size: 12, color: "#c3c2b7" },
  }));
  return { data, layout, height };
}
