/** Plotly figures for the bid-ask spline (curvature) study. Axis: z = Phi^-1(1 - call delta), increasing with strike. */
import { SERIES_COLORS, axis } from "../components/Plot";
import type { SplineExpiry } from "../types";

type Model = NonNullable<SplineExpiry["model"]>;
const VP = 100;                                   // curvature shown in vol points per z^2
const SPLINE = SERIES_COLORS[0], MODEL = SERIES_COLORS[1], TOUCH = SERIES_COLORS[3], BROKEN = "#e66767";
const SEG = "rgba(195,194,183,0.35)";

/** The stored smile model, moved onto this axis (its own z is Phi^-1(call delta) = -z). */
export const modelVol = (m: Model, z: number) =>
  m.sigma_atm - m.skew * z + m.kappa_put * Math.max(-z, 0) ** 2 + m.kappa_call * Math.max(z, 0) ** 2;

const zAxis = (extra: Record<string, unknown> = {}) =>
  axis({ title: { text: "z = Φ⁻¹(1 − call Δ)", standoff: 4 }, zeroline: true, ...extra });

/** Bid/ask bounds as slanted segments, the spline, and the stored model for comparison. */
export function smileFigure(e: SplineExpiry, showItm: boolean) {
  const p = e.points, segX: (number | null)[] = [], segY: (number | null)[] = [];
  const otm = (i: number) => (p.is_call[i] ? p.strike[i] >= e.forward : p.strike[i] < e.forward);
  const bid = { x: [] as number[], y: [] as number[], k: [] as number[] };
  const ask = { x: [] as number[], y: [] as number[], k: [] as number[] };
  const touch = { x: [] as number[], y: [] as number[] }, broken = { x: [] as number[], y: [] as number[], t: [] as string[] };
  p.strike.forEach((k, i) => {
    if (!showItm && !otm(i)) return;
    const [zb, vb, za, va] = [p.z_bid[i], p.iv_bid[i], p.z_ask[i], p.iv_ask[i]];
    if (zb != null && vb != null && za != null && va != null) segX.push(zb, za, null), segY.push(vb, va, null);
    if (zb != null && vb != null) {
      bid.x.push(zb); bid.y.push(vb); bid.k.push(k);
      if (p.bid_active[i]) touch.x.push(zb), touch.y.push(vb);
      if (p.bid_slack[i] > 0) broken.x.push(zb), broken.y.push(vb), broken.t.push(`K ${k} bid broken by ${(p.bid_slack[i] * VP).toFixed(2)} vp`);
    }
    if (za != null && va != null) {
      ask.x.push(za); ask.y.push(va); ask.k.push(k);
      if (p.ask_active[i]) touch.x.push(za), touch.y.push(va);
      if (p.ask_slack[i] > 0) broken.x.push(za), broken.y.push(va), broken.t.push(`K ${k} ask broken by ${(p.ask_slack[i] * VP).toFixed(2)} vp`);
    }
  });
  const marks = (pts: typeof bid, symbol: string, name: string) => ({
    type: "scatter", mode: "markers", name, x: pts.x, y: pts.y, customdata: pts.k,
    marker: { color: "#898781", size: 5, symbol, line: { color: "#898781", width: 1 } },
    hovertemplate: `K %{customdata:,.2f}<br>z %{x:.3f}<br>${name} %{y:.2%}<extra></extra>`,
  });
  const data: unknown[] = [
    { type: "scatter", mode: "lines", name: "bid–ask", x: segX, y: segY, line: { color: SEG, width: 1 }, hoverinfo: "skip" },
    marks(bid, "triangle-down", "bid"), marks(ask, "triangle-up-open", "ask"),
    { type: "scatter", mode: "lines", name: "spline", x: e.grid_z, y: e.s, line: { color: SPLINE, width: 2 },
      hovertemplate: "z %{x:.3f}<br>spline %{y:.2%}<extra></extra>" },
  ];
  if (e.model) {
    data.push({ type: "scatter", mode: "lines", name: "current model", x: e.grid_z, y: e.grid_z.map((z) => modelVol(e.model!, z)),
      line: { color: MODEL, width: 1.5, dash: "dash" }, hovertemplate: "z %{x:.3f}<br>model %{y:.2%}<extra></extra>" });
  }
  data.push({ type: "scatter", mode: "markers", name: "touching", x: touch.x, y: touch.y, hoverinfo: "skip",
    marker: { color: "rgba(0,0,0,0)", size: 11, line: { color: TOUCH, width: 1.5 } } });
  if (broken.x.length) {
    data.push({ type: "scatter", mode: "markers", name: "broken", x: broken.x, y: broken.y, text: broken.t,
      marker: { color: BROKEN, size: 9, symbol: "x" }, hovertemplate: "%{text}<extra></extra>" });
  }
  // Zoom to the smile: wide quotes would otherwise stretch the axis far past it.
  const lo = Math.min(...e.s), hi = Math.max(...e.s), pad = Math.max(0.3 * (hi - lo), 0.03);
  return { data, layout: { margin: { l: 52, r: 10, t: 10, b: 40 }, legend: { orientation: "h", y: 1.12, x: 0 },
    xaxis: zAxis(), yaxis: axis({ tickformat: ".0%", range: [Math.max(lo - pad, 0), hi + pad] }) } };
}

/** s''(z) of the spline against the model's step (2 kappa each side of z = 0), with the wing peaks. */
export function curvatureFigure(e: SplineExpiry) {
  const data: unknown[] = [
    { type: "scatter", mode: "lines", name: "spline s''", x: e.grid_z, y: e.s2.map((v) => v * VP), line: { color: SPLINE, width: 2 },
      hovertemplate: "z %{x:.3f}<br>s'' %{y:.2f} vp/z²<extra></extra>" },
  ];
  if (e.model && e.grid_z.length) {
    const lo = e.grid_z[0], hi = e.grid_z[e.grid_z.length - 1], kp = 2 * e.model.kappa_put * VP, kc = 2 * e.model.kappa_call * VP;
    data.push({ type: "scatter", mode: "lines", name: "current model (2κ)", x: [lo, 0, 0, hi], y: [kp, kp, kc, kc],
      line: { color: MODEL, width: 1.5, dash: "dash" }, hovertemplate: "model %{y:.2f} vp/z²<extra></extra>" });
  }
  const peaks = [e.put_peak, e.call_peak].filter((p) => p.z != null && p.s2 != null);
  data.push({ type: "scatter", mode: "markers", name: "wing peak", x: peaks.map((p) => p.z), y: peaks.map((p) => p.s2! * VP),
    text: peaks.map((p) => (p.interior ? "peak inside the quotes" : "at the outermost quote: still rising")),
    marker: { color: TOUCH, size: 10, symbol: peaks.map((p) => (p.interior ? "diamond" : "diamond-open")), line: { color: TOUCH, width: 1.5 } },
    hovertemplate: "z %{x:.2f}<br>s'' %{y:.2f} vp/z²<br>%{text}<extra></extra>" });
  return { data, layout: { margin: { l: 52, r: 10, t: 10, b: 40 }, legend: { orientation: "h", y: 1.12, x: 0 },
    xaxis: zAxis(), yaxis: axis({ title: { text: "s'' (vol pts / z²)", standoff: 4 } }) } };
}

/** Every expiry's s''(z) on one chart: lighter = longer dated. */
export function allCurvatureFigure(list: SplineExpiry[], selected: string) {
  const ok = list.filter((e) => e.status === "ok" && e.grid_z.length);
  const Ts = ok.map((e) => Math.sqrt(e.T)), lo = Math.min(...Ts), hi = Math.max(...Ts);
  const data = ok.map((e) => {
    const u = hi > lo ? (Math.sqrt(e.T) - lo) / (hi - lo) : 0.5;
    const sel = e.expiry === selected;
    return { type: "scatter", mode: "lines", name: e.expiry, x: e.grid_z, y: e.s2.map((v) => v * VP), customdata: e.grid_z.map(() => e.expiry),
      line: { color: sel ? SERIES_COLORS[1] : `hsl(212, 70%, ${30 + 50 * u}%)`, width: sel ? 2.5 : 1.2 },
      hovertemplate: `${e.expiry} (T ${e.T.toFixed(2)})<br>z %{x:.2f}<br>s'' %{y:.2f} vp/z²<extra></extra>` };
  });
  return { data, layout: { margin: { l: 52, r: 10, t: 10, b: 40 }, showlegend: false,
    xaxis: zAxis(), yaxis: axis({ title: { text: "s'' (vol pts / z²)", standoff: 4 } }) } };
}
