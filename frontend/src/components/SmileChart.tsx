import { useMemo } from "react";
import { X_LABELS, bidAskPoints, fittedCurve, hasFit, interp, midCurve, type Pt } from "../lib/smile";
import { seriesLabel } from "../lib/format";
import type { Compare, SeriesSpec, SmileOut, XMode } from "../types";
import { Plot, SERIES_COLORS, axis } from "./Plot";

interface Props {
  series: SeriesSpec[];
  smiles: Record<number, SmileOut | undefined>;
  xMode: XMode;
  /** With two or more series, a second panel underneath (same x axis) compares each one with the baseline. */
  compare: Compare | null;
}

const LEVELS_PX = 440, COMPARE_PX = 240;

function scatter(pts: Pt[], name: string, color: string, symbol: string, label: string, legendgroup: string) {
  return {
    x: pts.map((p) => p.x), y: pts.map((p) => p.y), customdata: pts.map((p) => p.strike),
    mode: "markers", type: "scatter", name, legendgroup,
    marker: { color, size: 7, symbol, line: { color, width: 1.2 } },
    hovertemplate: `K %{customdata:,.0f}<br>x %{x:.3f}<br>IV %{y:.2%}<extra>${label}</extra>`,
  };
}

function line(pts: Pt[], name: string, color: string, label: string, fmt: string, smooth = false) {
  return {
    x: pts.map((p) => p.x), y: pts.map((p) => p.y), customdata: pts.map((p) => p.strike),
    mode: smooth ? "lines" : "lines+markers", type: "scatter", name,
    line: { color, width: 2 }, marker: { color, size: 5 },
    hovertemplate: `K %{customdata:,.0f}<br>x %{x:.3f}<br>%{y:${fmt}}<extra>${label}</extra>`,
  };
}

export function SmileChart({ series, smiles, xMode, compare }: Props) {
  const stacked = compare !== null && series.length > 1;

  const { data, notes } = useMemo(() => {
    const traces: unknown[] = [];
    const notes = new Set<string>();
    const baseline = series.find((s) => s.baseline) ?? series[0];
    // A "fitted" series compares by its model curve, anything else by its mid.
    const curveOf = (spec: SeriesSpec, s: SmileOut) => (spec.type === "fitted" ? fittedCurve(s, xMode) : midCurve(s, xMode));
    const baseSmile = baseline ? smiles[baseline.id] : undefined;
    const baseCurve = baseSmile ? curveOf(baseline, baseSmile) : [];
    const ratio = compare === "ratio";

    series.forEach((spec, idx) => {
      const s = smiles[spec.id];
      if (!s) return;
      const color = SERIES_COLORS[idx % SERIES_COLORS.length];
      const label = seriesLabel(spec);
      if (spec.type === "fitted" && !hasFit(s)) {
        notes.add(`${label}: no stored fit for this expiry yet (fit it from the Underlyings tab).`);
        return;
      }

      // Top panel: the smile itself.
      if (spec.type === "bidask") {
        const { bid, ask } = bidAskPoints(s, xMode);
        traces.push(scatter(bid, `${label} bid`, color, "triangle-down", label, String(spec.id)));
        traces.push(scatter(ask, `${label} ask`, color, "triangle-up-open", label, String(spec.id)));
      } else if (spec.type === "fitted") {
        traces.push(line(fittedCurve(s, xMode), `${label} fitted`, color, label, ".2%", true));
      } else {
        traces.push(line(midCurve(s, xMode), `${label} mid`, color, label, ".2%"));
      }

      // Bottom panel: against the baseline, on the same x axis.
      if (!stacked) return;
      if (spec.id === baseline.id) {
        const xs = baseCurve.map((p) => p.x);
        traces.push({ x: xs, y: xs.map(() => (ratio ? 1 : 0)), yaxis: "y2", mode: "lines", type: "scatter", showlegend: false,
          line: { color, width: 1.5, dash: "dot" }, hoverinfo: "skip" });
        return;
      }
      const pts = curveOf(spec, s)
        .map((p) => ({ ...p, base: interp(baseCurve, p.x) }))
        .filter((p) => p.base != null && (!ratio || p.base > 0))
        .map((p) => ({ ...p, y: ratio ? p.y / (p.base as number) : p.y - (p.base as number) }));
      traces.push({ ...line(pts, `${label} ${ratio ? "÷" : "−"} baseline`, color, label, ratio ? ".3f" : "+.2%"), yaxis: "y2", showlegend: false });
      if (xMode === "strike" && s.name !== baseSmile?.name)
        notes.add("Strikes of different underlyings aren't comparable: use delta, z or moneyness to compare across names.");
    });
    return { data: traces, notes: [...notes] };
  }, [series, smiles, xMode, compare, stacked]);

  const height = stacked ? LEVELS_PX + COMPARE_PX : LEVELS_PX;
  const layout = useMemo(() => {
    const split = COMPARE_PX / (LEVELS_PX + COMPARE_PX);      // share of the figure the bottom panel gets
    return {
      margin: { l: 60, r: 16, t: 10, b: 44 },
      xaxis: axis({ title: { text: X_LABELS[xMode] }, anchor: stacked ? "y2" : "y" }),
      yaxis: axis({ title: { text: "implied vol" }, tickformat: ".0%", domain: stacked ? [split + 0.06, 1] : [0, 1] }),
      ...(stacked && {
        yaxis2: axis({
          domain: [0, split - 0.02],
          title: { text: compare === "ratio" ? "÷ baseline" : "− baseline" },
          tickformat: compare === "ratio" ? ".2f" : "+.1%",
        }),
      }),
      legend: { orientation: "h", y: -70 / height, font: { size: 10.5 } },
    };
  }, [xMode, stacked, compare, height]);

  return (
    <>
      <Plot data={data} layout={layout} height={height + 40} />
      {notes.map((n) => (
        <div key={n} className="note">{n}</div>
      ))}
    </>
  );
}
