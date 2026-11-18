import { useEffect, useState } from "react";
import { api } from "../api";
import { ParamsPanel } from "../components/ParamsPanel";
import { Seg, X_OPTIONS } from "../components/Seg";
import { SeriesPanel } from "../components/SeriesPanel";
import { SmileChart } from "../components/SmileChart";
import { SmileGrid } from "../components/SmileGrid";
import { seriesLabel } from "../lib/format";
import type { NameOut, SeriesSpec, SmileOut, XMode } from "../types";

interface Props {
  names: NameOut[];
  series: SeriesSpec[];
  setSeries: (updater: (prev: SeriesSpec[]) => SeriesSpec[]) => void;
  /** Bumped when a fresh series is loaded in here from elsewhere ("Plot" buttons, grid cells). */
  resetKey: number;
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

type View = "single" | "grid";

export function PlotsPage({ names, series, setSeries, resetKey, onOpenInPlots }: Props) {
  const [view, setView] = useState<View>("single");
  const [xMode, setXMode] = useState<XMode>("delta");
  useEffect(() => setView("single"), [resetKey]);
  const [focusedId, setFocusedId] = useState<number | null>(null);
  const [smiles, setSmiles] = useState<Record<number, SmileOut | undefined>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});

  useEffect(() => {
    let live = true;
    series.forEach((s) => {
      api.smile(s.name, s.snapshot, s.expiry).then(
        (smile) => {
          if (!live) return;
          setSmiles((m) => ({ ...m, [s.id]: smile }));
          setErrors((e) => Object.fromEntries(Object.entries(e).filter(([k]) => Number(k) !== s.id)));
        },
        (err: Error) => {
          if (live) setErrors((e) => ({ ...e, [s.id]: err.message }));
        },
      );
    });
    return () => { live = false; };
  }, [series]);

  async function addSeries() {
    // New series defaults to the same smile one snapshot earlier -- the most common comparison.
    const from = series.find((s) => s.id === focusedId) ?? series[series.length - 1];
    const snaps = await api.snapshots(from.name);
    const older = snaps[snaps.indexOf(from.snapshot) + 1] ?? from.snapshot;
    const id = Math.max(...series.map((s) => s.id)) + 1;
    setSeries((prev) => [...prev, { ...from, id, snapshot: older, baseline: false }]);
    setFocusedId(id);
  }

  const focused = series.find((s) => s.id === focusedId) ?? series[series.length - 1];
  const viewSwitch = (
    <div className="field"><span className="field-label">View</span>
      <Seg label="View" value={view} onChange={setView} options={[{ value: "single", label: "Single" }, { value: "grid", label: "Grid" }]} />
    </div>
  );

  return (
    <>
      <div hidden={view !== "single"}>
        <div className="toolbar">
          {viewSwitch}
          <div className="field"><span className="field-label">X axis</span>
            <Seg label="X axis" value={xMode} options={X_OPTIONS} onChange={setXMode} />
          </div>
        </div>

        <div className="plots-layout">
          <div className="side-stack">
            <div className="panel chart-box">
              <SmileChart series={series} smiles={smiles} xMode={xMode} yMode="levels" height={440} />
              {series.filter((s) => errors[s.id]).map((s) => <div key={s.id} className="note error">{seriesLabel(s)}: {errors[s.id]}</div>)}
            </div>
            {series.length > 1 && (
              <div className="panel">
                <div className="panel-head" title="Each series' mid (or fitted curve, for a fitted series) minus the baseline's. Pick the baseline in the series list.">
                  Difference vs baseline
                </div>
                <div className="chart-box"><SmileChart series={series} smiles={smiles} xMode={xMode} yMode="diff" height={260} /></div>
              </div>
            )}
          </div>
          <div className="side-stack">
            <SeriesPanel series={series} names={names} focusedId={focused?.id ?? null} showBaseline={series.length > 1}
              onChange={setSeries} onFocus={setFocusedId} onAdd={addSeries} />
            <ParamsPanel smile={focused ? smiles[focused.id] : undefined} />
          </div>
        </div>
      </div>
      {view === "grid" && <SmileGrid names={names} viewSwitch={viewSwitch} onOpenInPlots={onOpenInPlots} />}
    </>
  );
}
