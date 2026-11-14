import { useState } from "react";
import { CurvatureStudy } from "../components/CurvatureStudy";
import { ParamStudy } from "../components/ParamStudy";
import { Seg } from "../components/Seg";
import type { NameOut, SeriesSpec } from "../types";

interface Props {
  names: NameOut[];
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

type View = "params" | "curvature";

/** Two studies of the fitted smiles; each stays mounted (keeps its state) once opened. */
export function AnalysisPage({ names, onOpenInPlots }: Props) {
  const [view, setView] = useState<View>("params");
  const [opened, setOpened] = useState<Set<View>>(new Set(["params"]));
  const show = (v: View) => { setView(v); setOpened((o) => new Set(o).add(v)); };
  return (
    <>
      <div className="analysis-views">
        <Seg label="Study" value={view} onChange={show} options={[
          { value: "params", label: "Parameters vs T" }, { value: "curvature", label: "Curvature study (bid–ask spline)" }]} />
      </div>
      <div hidden={view !== "params"}><ParamStudy names={names} onOpenInPlots={onOpenInPlots} /></div>
      {opened.has("curvature") && <div hidden={view !== "curvature"}><CurvatureStudy names={names} /></div>}
    </>
  );
}
