import { type ReactNode, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { allCurvatureFigure, curvatureFigure, smileFigure } from "../lib/curvature";
import { fmtNum } from "../lib/format";
import type { NameOut, SplineExpiry } from "../types";
import { NameSnapshotFields, useNameSnapshot } from "./NameSnapshotPicker";
import { Plot } from "./Plot";

const vp = (v: number | null | undefined) => (v == null ? "—" : (v * 100).toFixed(2));
const ABOUT = "The smoothest-curvature curve that passes on or above every bid and on or below every ask. "
  + "Curvature only bends where the quotes force it, so a peak is demanded by the market. Curvature in vol points per z². "
  + "Quotes wider than 15 vol points are left out. Nothing is stored.";

/** Bid-ask spline study: the smoothest-curvature curve between every bid and ask, per expiry. */
export function CurvatureStudy({ names, viewSwitch }: { names: NameOut[]; viewSwitch: ReactNode }) {
  const picker = useNameSnapshot(names);
  const { name, snapshot } = picker;
  const [list, setList] = useState<SplineExpiry[] | null>(null);
  const [expiry, setExpiry] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!name || !snapshot) return;
    let live = true;
    setList(null); setError("");
    api.splineStudy(name, snapshot).then((l) => {
      if (!live) return;
      setList(l);
      setExpiry((x) => (l.some((e) => e.expiry === x && e.status === "ok") ? x : l.find((e) => e.status === "ok")?.expiry ?? ""));
    }, (e: Error) => live && setError(e.message));
    return () => { live = false; };
  }, [name, snapshot]);

  const sel = list?.find((e) => e.expiry === expiry);
  const [showItm, setShowItm] = useState(false);
  const smile = useMemo(() => (sel && sel.status === "ok" ? smileFigure(sel, showItm) : null), [sel, showItm]);
  const curv = useMemo(() => (sel && sel.status === "ok" ? curvatureFigure(sel) : null), [sel]);
  const all = useMemo(() => (list ? allCurvatureFigure(list, expiry) : null), [list, expiry]);
  const pick = (cd: unknown) => typeof cd === "string" && setExpiry(cd);   // click a line to select its expiry

  return (
    <>
      <div className="toolbar">
        {viewSwitch}
        <NameSnapshotFields picker={picker} names={names} />
        <label className="field"><span className="field-label">Expiry</span>
          <select value={expiry} onChange={(e) => setExpiry(e.target.value)}>
            {(list ?? []).filter((e) => e.status === "ok").map((e) => <option key={e.expiry}>{e.expiry}</option>)}
          </select>
        </label>
        <label className="check-label" title="In-the-money quotes are fitted too; they're hidden only to keep the chart readable">
          <input type="checkbox" checked={showItm} onChange={(e) => setShowItm(e.target.checked)} /> In-the-money quotes
        </label>
        {sel && <span className="muted toolbar-hint">
          T {sel.T.toFixed(3)} · F {fmtNum(sel.forward, 2)} · {sel.n_bounds} bounds, {sel.n_active} touching
          {sel.n_broken ? `, ${sel.n_broken} broken (max ${vp(sel.max_break)} vp)` : ", none broken"}
          {sel.monotone_ok ? "" : " · strike→delta not one-to-one somewhere"}</span>}
        {error && <span className="error-text toolbar-hint">{error}</span>}
      </div>

      {list === null && !error ? <div className="panel muted empty">Fitting every expiry…</div> : (
        <>
          <div className="curv-pair">
            <div className="panel"><div className="panel-head" title={ABOUT}>Smile: bid–ask bounds, spline, model <span className="muted">ⓘ</span></div>
              {smile ? <Plot data={smile.data} layout={smile.layout} height={340} /> : <div className="muted empty">No fit for this expiry.</div>}
            </div>
            <div className="panel"><div className="panel-head">Curvature s''(z)</div>
              {curv ? <Plot data={curv.data} layout={curv.layout} height={340} /> : <div className="muted empty">No fit for this expiry.</div>}
            </div>
          </div>
          <div className="panel" style={{ marginTop: 14 }}>
            <div className="panel-head" title="Lighter = longer dated, orange = selected. Click a line to select that expiry.">Curvature across expiries</div>
            {all && <Plot data={all.data} layout={all.layout} height={300} onPointClick={pick} />}
          </div>
        </>
      )}
    </>
  );
}
