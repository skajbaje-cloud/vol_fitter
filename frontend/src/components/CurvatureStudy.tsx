import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { allCurvatureFigure, curvatureFigure, smileFigure } from "../lib/curvature";
import { fmtNum, fmtTs } from "../lib/format";
import type { NameOut, SplineExpiry, WingPeak } from "../types";
import { Plot } from "./Plot";

const vp = (v: number | null | undefined) => (v == null ? "—" : (v * 100).toFixed(2));
const peak = (p: WingPeak) => (p.z == null ? "—" : `${p.z.toFixed(2)} · ${vp(p.s2)}${p.interior ? "" : " (edge)"}`);

/** Bid-ask spline study: the smoothest-curvature curve between every bid and ask, per expiry. */
export function CurvatureStudy({ names }: { names: NameOut[] }) {
  const [name, setName] = useState(names[0]?.name ?? "");
  const [snaps, setSnaps] = useState<string[]>([]);
  const [snapshot, setSnapshot] = useState("");
  const [list, setList] = useState<SplineExpiry[] | null>(null);
  const [expiry, setExpiry] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!name) return;
    api.snapshots(name).then((s) => { setSnaps(s); setSnapshot(s[0] ?? ""); }, (e: Error) => setError(e.message));
  }, [name]);

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
        <label className="field"><span className="field-label">Underlying</span>
          <select value={name} onChange={(e) => setName(e.target.value)}>
            {names.map((n) => <option key={n.name}>{n.name}</option>)}
          </select>
        </label>
        <label className="field"><span className="field-label">Snapshot</span>
          <select value={snapshot} onChange={(e) => setSnapshot(e.target.value)}>
            {snaps.map((s) => <option key={s} value={s}>{fmtTs(s)}</option>)}
          </select>
        </label>
        <label className="field"><span className="field-label">Expiry</span>
          <select value={expiry} onChange={(e) => setExpiry(e.target.value)}>
            {(list ?? []).filter((e) => e.status === "ok").map((e) => <option key={e.expiry}>{e.expiry}</option>)}
          </select>
        </label>
        <label className="check-label" title="In-the-money quotes are fitted too; they're hidden only to keep the chart readable">
          <input type="checkbox" checked={showItm} onChange={(e) => setShowItm(e.target.checked)} /> Show in-the-money quotes
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
            <div className="panel"><div className="panel-head">Smile: bid–ask bounds, spline, current model</div>
              {smile ? <Plot data={smile.data} layout={smile.layout} height={340} /> : <div className="muted empty">No fit for this expiry.</div>}
            </div>
            <div className="panel"><div className="panel-head">Curvature s''(z)</div>
              {curv ? <Plot data={curv.data} layout={curv.layout} height={340} /> : <div className="muted empty">No fit for this expiry.</div>}
            </div>
          </div>
          <div className="panel" style={{ marginTop: 14 }}>
            <div className="panel-head">Curvature across expiries <span className="muted">· lighter = longer dated, orange = selected, click a line to select it</span></div>
            {all && <Plot data={all.data} layout={all.layout} height={300} onPointClick={pick} />}
          </div>
          <div className="panel" style={{ marginTop: 14 }}>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr>
                  <th>Expiry</th><th>T</th><th>Bounds</th><th>Touching</th><th>Broken</th><th>s''(0)</th>
                  <th>Put peak z · s''</th><th>Call peak z · s''</th><th>Model 2κ put</th><th>Model 2κ call</th>
                </tr></thead>
                <tbody>
                  {(list ?? []).map((e) => (
                    <tr key={e.expiry} className={e.expiry === expiry ? "open" : ""} style={{ cursor: e.status === "ok" ? "pointer" : undefined }}
                      onClick={() => e.status === "ok" && setExpiry(e.expiry)}>
                      <td className="name">{e.expiry}</td><td>{e.T.toFixed(3)}</td>
                      {e.status !== "ok" ? <td colSpan={8} className="muted">{e.message}</td> : (<>
                        <td>{e.n_bounds}</td><td>{e.n_active}</td>
                        <td>{e.n_broken ? `${e.n_broken} (≤ ${vp(e.max_break)} vp)` : <span className="muted">0</span>}</td>
                        <td>{vp(e.s2_atm)}</td><td>{peak(e.put_peak)}</td><td>{peak(e.call_peak)}</td>
                        <td>{e.model ? vp(2 * e.model.kappa_put) : "—"}</td><td>{e.model ? vp(2 * e.model.kappa_call) : "—"}</td>
                      </>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
      <div className="note">
        The curve is the smoothest-curvature one (least ∫s‴²) that passes on or above every bid and on or below every ask;
        each quote's bid and ask sit at their own z, so bounds are slanted segments. Curvature varies only where the quotes
        force it, so a peak here is demanded by the market. "Edge" means the peak is at the outermost quote. Curvature in vol
        points per z². A bound is "broken" only when no smooth curve can respect it (conflicting quotes). Quotes wider than
        15 vol points are left out (placeholder markets carry no information). Nothing is stored.
      </div>
    </>
  );
}
