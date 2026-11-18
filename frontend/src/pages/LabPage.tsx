import { type ReactNode, useEffect, useMemo, useState } from "react";
import { api, nearestExpiry } from "../api";
import { CurvatureStudy } from "../components/CurvatureStudy";
import { LabCharts } from "../components/LabCharts";
import { NameSnapshotFields, useNameSnapshot } from "../components/NameSnapshotPicker";
import { ParamSliders } from "../components/ParamSliders";
import { ParamStudy } from "../components/ParamStudy";
import { Seg } from "../components/Seg";
import { StepSelect } from "../components/StepSelect";
import { type LabAxis, type ZParams, evaluate, fittedParams, guessParams } from "../lib/zquad";
import type { NameOut, SeriesSpec, SmileOut } from "../types";

type View = "smile" | "curvature" | "params";
const VIEWS = [
  { value: "smile" as const, label: "Smile" },
  { value: "curvature" as const, label: "Curvature" },
  { value: "params" as const, label: "Parameters vs T" },
];

interface Props {
  names: NameOut[];
  active: boolean;                 // the Lab tab is showing
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

/** Three ways to look at the model; nothing here is stored. Each view keeps its state once opened. */
export function LabPage({ names, active, onOpenInPlots }: Props) {
  const [view, setView] = useState<View>("smile");
  const [opened, setOpened] = useState<Set<View>>(new Set(["smile"]));
  const show = (v: View) => { setView(v); setOpened((o) => new Set(o).add(v)); };
  const viewSwitch = (
    <div className="field"><span className="field-label">View</span><Seg label="Lab view" value={view} onChange={show} options={VIEWS} /></div>
  );
  return (
    <>
      <div hidden={view !== "smile"}><SmileLab names={names} viewSwitch={viewSwitch} /></div>
      {opened.has("curvature") && <div hidden={view !== "curvature"}><CurvatureStudy names={names} viewSwitch={viewSwitch} /></div>}
      {opened.has("params") && (
        <div hidden={view !== "params"}>
          <ParamStudy names={names} viewSwitch={viewSwitch} active={active && view === "params"} onOpenInPlots={onOpenInPlots} />
        </div>
      )}
    </>
  );
}

const AXES = [
  { value: "delta" as const, label: "1 − call Δ" },
  { value: "z" as const, label: "Φ⁻¹(1 − call Δ)" },
];

/** Drag the four smile parameters and see how the curve sits against the quotes. */
function SmileLab({ names, viewSwitch }: { names: NameOut[]; viewSwitch: ReactNode }) {
  const picker = useNameSnapshot(names);
  const { name, snapshot } = picker;
  const [mats, setMats] = useState<string[]>([]);
  const [expiry, setExpiry] = useState("");
  const [smile, setSmile] = useState<SmileOut | null>(null);
  const [p, setP] = useState<ZParams | null>(null);
  const [ax, setAx] = useState<LabAxis>("delta");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!snapshot) return;
    api.maturities(name, snapshot).then((m) => {
      setMats(m);
      setExpiry((prev) => nearestExpiry(m, prev || m[Math.min(4, m.length - 1)] || "") ?? "");
    });
  }, [name, snapshot]);

  useEffect(() => {
    if (!snapshot || !expiry || !mats.includes(expiry)) return;
    let live = true;
    api.smile(name, snapshot, expiry).then(
      (s) => { if (!live) return; setSmile(s); setP(fittedParams(s) ?? guessParams(s)); setError(""); },
      (e: Error) => live && setError(e.message),
    );
    return () => { live = false; };
  }, [name, snapshot, expiry, mats]);

  const fitted = smile ? fittedParams(smile) : null;
  const result = useMemo(() => (smile && p ? evaluate(smile, p, ax) : null), [smile, p, ax]);

  return (
    <>
      <div className="toolbar">
        {viewSwitch}
        <NameSnapshotFields picker={picker} names={names} step />
        <div className="field"><span className="field-label">Expiry</span>
          <StepSelect label="expiry" value={expiry} onChange={setExpiry} options={mats.map((m) => ({ value: m, label: m }))} />
        </div>
        <div className="field"><span className="field-label">X axis</span>
          <Seg label="X axis" value={ax} options={AXES} onChange={setAx} /></div>
      </div>

      {error && <div className="note error">{error}</div>}
      {smile && p && result && (
        <div className="plots-layout">
          <div className="panel"><LabCharts points={result.points} p={p} ax={ax} /></div>
          <ParamSliders p={p} fitted={fitted} stats={result.stats} onChange={setP}
            onReset={() => setP(fitted ?? guessParams(smile))} />
        </div>
      )}
    </>
  );
}
