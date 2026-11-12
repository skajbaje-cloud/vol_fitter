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
  onPointClick?: (customdata: unknown) => void;   // receives the clicked point's customdata
}

type PlotlyEl = HTMLDivElement & { on?: (ev: string, fn: (e: { points: { customdata: unknown }[] }) => void) => void };

export function Plot({ data, layout, height, onPointClick }: Props) {
  const ref = useRef<PlotlyEl>(null);
  const click = useRef(onPointClick);
  click.current = onPointClick;
  const bound = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    Plotly.react(el, data, { ...BASE_LAYOUT, ...layout }, CONFIG).then(() => {
      // Plotly adds .on() to the element on first draw; bind once and read the latest handler through the ref.
      if (bound.current || !el.on) return;
      bound.current = true;
      el.on("plotly_click", (e) => { const p = e.points[0]; if (p && click.current) click.current(p.customdata); });
    });
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
      bound.current = false;
    };
  }, []);

  return <div ref={ref} style={{ height }} />;
}
