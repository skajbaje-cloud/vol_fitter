import { useMemo } from "react";
import { type LabAxis, type LabPoint, type ZParams, ppf, terms, xOf, zOf } from "../lib/zquad";
import { Plot, axis } from "./Plot";

// Colours mirror the CSS tokens: accent = inside, critical = outside.
const INSIDE = "#3987e5", OUTSIDE = "#e66767", CURVE = "#f0efec", MUTED = "#898781";
const BAND = "rgba(57, 135, 229, 0.16)";

const GRID_DELTAS = Array.from({ length: 401 }, (_, k) => 0.002 + (0.996 * k) / 400);

function frame(ax: LabAxis) {
  const x15 = [xOf(ax, 0.85), xOf(ax, 0.15)];   // 15Δ put (call Δ 0.85) and 15Δ call
  return {
    range: ax === "delta" ? [0, 1] : [-3, 3],
    shapes: x15.map((x) => ({ type: "line", x0: x, x1: x, yref: "paper", y0: 0, y1: 1, line: { color: MUTED, width: 1, dash: "dot" } })),
    labels: x15.map((x, k) => ({ x, yref: "paper", y: 1, yanchor: "bottom", showarrow: false, text: k ? "15Δ call" : "15Δ put", font: { size: 10, color: MUTED } })),
  };
}

interface Props { points: LabPoint[]; p: ZParams; ax: LabAxis }

export function LabCharts({ points, p, ax }: Props) {
  const f = useMemo(() => frame(ax), [ax]);
  const gx = useMemo(() => GRID_DELTAS.map((d) => xOf(ax, d)), [ax]);

  const smile = useMemo(() => {
    const curve = GRID_DELTAS.map((d) => { const t = terms(p, zOf(d)); return t.line + t.put + t.call; });
    const marks = (side: "bid" | "ask", ok: boolean) => {
      const pts = points.filter((q) => q.inside === ok && q[side] != null);
      const col = ok ? INSIDE : OUTSIDE;
      return {
        x: pts.map((q) => q.x), y: pts.map((q) => q[side]), type: "scatter", mode: "markers",
        text: pts.map((q) => `${q.isCall ? "C" : "P"} ${q.strike.toLocaleString()}<br>bid ${pct(q.bid)} · ask ${pct(q.ask)}<br>model ${pct(q.model)}`),
        hovertemplate: "%{text}<extra></extra>",
        marker: { symbol: side === "bid" ? "triangle-down" : "triangle-up", size: 7, color: side === "bid" ? col : "rgba(0,0,0,0)", line: { color: col, width: 1.2 } },
      };
    };
    return [marks("bid", true), marks("ask", true), marks("bid", false), marks("ask", false),
      { x: gx, y: curve, type: "scatter", mode: "lines", hoverinfo: "skip", line: { color: CURVE, width: 2.2 } }];
  }, [points, p, gx]);

  const resid = useMemo(() => {
    const two = points.filter((q) => q.resid != null).sort((a, b) => a.x - b.x);
    const xs = two.map((q) => q.x);
    return [
      { x: xs.concat([...xs].reverse()), y: two.map((q) => q.half! * 100).concat(two.map((q) => -q.half! * 100).reverse()),
        type: "scatter", mode: "lines", fill: "toself", fillcolor: BAND, line: { width: 0 }, hoverinfo: "skip" },
      { x: xs, y: two.map((q) => q.resid! * 100), type: "scatter", mode: "markers", hovertemplate: "%{y:+.2f} vol pts<extra></extra>",
        marker: { size: 5, color: two.map((q) => (Math.abs(q.resid!) <= q.half! + 1e-9 ? INSIDE : OUTSIDE)) } },
    ];
  }, [points]);

  const convex = useMemo(() => {
    // d²σ/dx² with x = call Δ − 0.5, by central differences on the model curve
    const ds = GRID_DELTAS.filter((d) => d > 0.02 && d < 0.98), h = 1e-3;
    const vol = (d: number) => { const t = terms(p, ppf(d)); return t.line + t.put + t.call; };
    const y = ds.map((d) => (vol(d + h) - 2 * vol(d) + vol(d - h)) / (h * h));
    return [{ x: ds.map((d) => xOf(ax, d)), y, type: "scatter", mode: "lines", hovertemplate: "%{y:.2f}<extra></extra>", line: { color: CURVE, width: 2 } }];
  }, [p, ax]);

  const xTitle = ax === "delta" ? "1 − call delta (puts left, calls right)" : "Φ⁻¹(1 − call delta), wings stretched";
  const layouts = useMemo(() => ({
    smile: { margin: { l: 50, r: 12, t: 20, b: 40 }, showlegend: false, shapes: f.shapes, annotations: f.labels,
      xaxis: axis({ range: f.range, title: { text: xTitle } }), yaxis: axis({ range: [0.08, 0.5], tickformat: ".0%", title: { text: "implied vol" } }) },
    resid: { margin: { l: 50, r: 12, t: 6, b: 30 }, showlegend: false, shapes: f.shapes,
      xaxis: axis({ range: f.range }), yaxis: axis({ range: [-2.5, 2.5], title: { text: "vol pts" } }) },
    convex: { margin: { l: 50, r: 12, t: 6, b: 30 }, showlegend: false, shapes: f.shapes,
      xaxis: axis({ range: f.range }), yaxis: axis({ title: { text: "vol / x²" } }) },
  }), [f, xTitle]);

  return (
    <>
      <div className="panel-head">Implied vol vs bid / ask</div>
      <div className="chart-box"><Plot data={smile} layout={layouts.smile} height={440} /></div>
      <div className="lab-legend">
        <span><i style={{ background: INSIDE }} />inside (▽ bid, △ ask)</span>
        <span><i style={{ background: OUTSIDE }} />outside</span>
        <span><i style={{ background: CURVE }} />model</span>
      </div>
      <div className="panel-head">Model − mid, vol points (two-sided quotes; band = ± half-spread, floored like the fitter)</div>
      <div className="chart-box"><Plot data={resid} layout={layouts.resid} height={200} /></div>
      <div className="panel-head">Local convexity d²σ/dx², x = call Δ − 0.5</div>
      <div className="chart-box"><Plot data={convex} layout={layouts.convex} height={180} /></div>
    </>
  );
}

const pct = (v: number | null) => (v == null ? "–" : `${(v * 100).toFixed(2)}`);
