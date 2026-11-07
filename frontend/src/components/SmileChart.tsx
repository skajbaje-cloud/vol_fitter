import { useMemo } from "react";
import { X_LABELS, bidAskPoints, hasFit, interp, midCurve, type Pt } from "../lib/smile";
import { seriesLabel } from "../lib/format";
import type { SeriesSpec, SmileOut, XMode, YMode } from "../types";
import { Plot, SERIES_COLORS, axis } from "./Plot";

interface Props {
  series: SeriesSpec[];
  smiles: Record<number, SmileOut | undefined>;
  xMode: XMode;
  yMode: YMode;
  height?: number;
}

function scatter(pts: Pt[], name: string, color: string, symbol: string, label: string, legendgroup: string) {
  return {
    x: pts.map((p) => p.x), y: pts.map((p) => p.y), customdata: pts.map((p) => p.strike),
    mode: "markers", type: "scatter", name, legendgroup,
    marker: { color, size: 7, symbol, line: { color, width: 1.2 } },
    hovertemplate: `K %{customdata:,.0f}<br>x %{x:.3f}<br>IV %{y:.2%}<extra>${label}</extra>`,
  };
}

function line(pts: Pt[], name: string, color: string, label: string, fmt: string) {
  return {
    x: pts.map((p) => p.x), y: pts.map((p) => p.y), customdata: pts.map((p) => p.strike),
    mode: "lines+markers", type: "scatter", name,
    line: { color, width: 2 }, marker: { color, size: 5 },
    hovertemplate: `K %{customdata:,.0f}<br>x %{x:.3f}<br>%{y:${fmt}}<extra>${label}</extra>`,
  };
}

export function SmileChart({ series, smiles, xMode, yMode, height = 500 }: Props) {
  const { data, notes } = useMemo(() => {
    const traces: unknown[] = [];
    const notes = new Set<string>();
    const baseline = series.find((s) => s.baseline) ?? series[0];
    const baseSmile = baseline ? smiles[baseline.id] : undefined;
    const baseCurve = baseSmile ? midCurve(baseSmile, xMode) : [];
    if (yMode === "diff" && series.length < 2)
      notes.add("Difference mode subtracts the baseline from the other series — add a second series to compare.");

    series.forEach((spec, idx) => {
      const s = smiles[spec.id];
      if (!s) return;
      const color = SERIES_COLORS[idx % SERIES_COLORS.length];
      const label = seriesLabel(spec);
      if (spec.type === "fitted" && !hasFit(s)) {
        notes.add("Fitted curves appear once per-expiry fitting exists (Phase 2); nothing to draw for “Fitted” yet.");
        return;
      }

      if (yMode === "diff") {
        if (spec.id === baseline.id) {
          const xs = baseCurve.map((p) => p.x);
          traces.push({ x: xs, y: xs.map(() => 0), mode: "lines", type: "scatter", name: `${label} (baseline)`,
            line: { color, width: 1.5, dash: "dot" }, hoverinfo: "skip" });
          return;
        }
        const diff = midCurve(s, xMode)
          .map((p) => ({ ...p, base: interp(baseCurve, p.x) }))
          .filter((p) => p.base != null)
          .map((p) => ({ ...p, y: p.y - (p.base as number) }));
        traces.push(line(diff, `${label} − baseline`, color, label, "+.2%"));
        if (xMode === "strike" && s.name !== baseSmile?.name)
          notes.add("Strikes of different underlyings aren't comparable — use delta or moneyness to diff across names.");
        return;
      }

      if (spec.type === "bidask") {
        const { bid, ask } = bidAskPoints(s, xMode);
        traces.push(scatter(bid, `${label} bid`, color, "triangle-down", label, String(spec.id)));
        traces.push(scatter(ask, `${label} ask`, color, "triangle-up-open", label, String(spec.id)));
      } else {
        traces.push(line(midCurve(s, xMode), `${label} mid`, color, label, ".2%"));
      }
    });
    return { data: traces, notes: [...notes] };
  }, [series, smiles, xMode, yMode]);

  const layout = useMemo(
    () => ({
      margin: { l: 56, r: 16, t: 10, b: 44 },
      xaxis: axis({ title: { text: X_LABELS[xMode] } }),
      yaxis: axis({
        title: { text: yMode === "diff" ? "Δ implied vol vs baseline (mid)" : "implied vol" },
        tickformat: yMode === "diff" ? "+.1%" : ".0%",
      }),
      legend: { orientation: "h", y: -0.16, font: { size: 10.5 } },
    }),
    [xMode, yMode],
  );

  return (
    <>
      <Plot data={data} layout={layout} height={height} />
      {notes.map((n) => (
        <div key={n} className="note">{n}</div>
      ))}
    </>
  );
}
