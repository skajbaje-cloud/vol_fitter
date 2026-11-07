import Plotly from "plotly.js-basic-dist-min";
import { useEffect, useRef } from "react";

// Chart chrome mirrors the CSS tokens in styles.css.
export const SERIES_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#2fbf2f", "#9085e9", "#e66767"];
const GRID = "#2c2c2a";
const AXIS = "#383835";

export function axis(extra: Record<string, unknown> = {}) {
  return { gridcolor: GRID, zerolinecolor: AXIS, linecolor: AXIS, ...extra };
}

const BASE_LAYOUT = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#c3c2b7", family: "system-ui, -apple-system, 'Segoe UI', sans-serif", size: 11.5 },
  hovermode: "closest",
  hoverlabel: { bgcolor: "#201f1d", bordercolor: "#383835", font: { color: "#f0efec" } },
};

const CONFIG = { displayModeBar: false, responsive: true };

interface Props {
  data: unknown[];
  layout: Record<string, unknown>;
  height: number;
}

export function Plot({ data, layout, height }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) Plotly.react(ref.current, data, { ...BASE_LAYOUT, ...layout }, CONFIG);
  }, [data, layout]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Pages stay mounted while hidden; resize once they become visible again.
    const ro = new ResizeObserver(() => el.offsetWidth > 0 && Plotly.Plots.resize(el));
    ro.observe(el);
    return () => {
      ro.disconnect();
      Plotly.purge(el);
    };
  }, []);

  return <div ref={ref} style={{ height }} />;
}
