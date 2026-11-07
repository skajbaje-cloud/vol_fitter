import { useEffect, useState } from "react";
import { api } from "../api";
import { ParamsPanel } from "../components/ParamsPanel";
import { Seg, X_OPTIONS } from "../components/Seg";
import { SeriesPanel } from "../components/SeriesPanel";
import { SmileChart } from "../components/SmileChart";
import type { NameOut, SeriesSpec, SmileOut, XMode, YMode } from "../types";

interface Props {
  names: NameOut[];
  series: SeriesSpec[];
  setSeries: (updater: (prev: SeriesSpec[]) => SeriesSpec[]) => void;
  /** Bumped when another page loads a fresh series in here, e.g. Grid's "open in Plots". */
  resetKey: number;
}

export function PlotsPage({ names, series, setSeries, resetKey }: Props) {
  const [xMode, setXMode] = useState<XMode>("delta");
  const [yMode, setYMode] = useState<YMode>("levels");
  useEffect(() => setYMode("levels"), [resetKey]);
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
  const errorList = Object.entries(errors);

  return (
    <>
      <div className="toolbar">
        <div className="field"><span className="field-label">X axis</span>
          <Seg label="X axis" value={xMode} options={X_OPTIONS} onChange={setXMode} />
        </div>
        <div className="field"><span className="field-label">Y axis</span>
          <Seg label="Y axis" value={yMode} onChange={setYMode} options={[
            { value: "levels", label: "Levels" },
            { value: "diff", label: "Difference" },
          ]} />
        </div>
        <div className="toolbar-hint muted">
          {yMode === "diff"
            ? "Each series is drawn as its mid IV minus the baseline series' mid IV."
            : "Bid ▽ and ask △ share their series' color. One-sided quotes are hidden."}
        </div>
      </div>

      <div className="plots-layout">
        <div className="panel">
          <div className="panel-head">Implied vol smile</div>
          <div className="chart-box">
            <SmileChart series={series} smiles={smiles} xMode={xMode} yMode={yMode} />
            {errorList.map(([id, msg]) => <div key={id} className="note error">Series #{id}: {msg}</div>)}
          </div>
        </div>
        <div className="side-stack">
          <SeriesPanel series={series} names={names} focusedId={focused?.id ?? null}
            onChange={setSeries} onFocus={setFocusedId} onAdd={addSeries} />
          <ParamsPanel smile={focused ? smiles[focused.id] : undefined} />
        </div>
      </div>
    </>
  );
}
