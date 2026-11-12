import { useEffect, useMemo, useState } from "react";
import { api, nearestExpiry } from "../api";
import { LabCharts } from "../components/LabCharts";
import { ParamSliders } from "../components/ParamSliders";
import { Seg } from "../components/Seg";
import { fmtTs } from "../lib/format";
import { type LabAxis, type ZParams, evaluate, fittedParams, guessParams } from "../lib/zquad";
import type { NameOut, SmileOut } from "../types";

const AXES = [
  { value: "delta" as const, label: "1 − call Δ" },
  { value: "z" as const, label: "Φ⁻¹(1 − call Δ)" },
];

export function LabPage({ names }: { names: NameOut[] }) {
  const [name, setName] = useState(names[0]?.name ?? "");
  const [snaps, setSnaps] = useState<string[]>([]);
  const [snapshot, setSnapshot] = useState("");
  const [mats, setMats] = useState<string[]>([]);
  const [expiry, setExpiry] = useState("");
  const [smile, setSmile] = useState<SmileOut | null>(null);
  const [p, setP] = useState<ZParams | null>(null);
  const [ax, setAx] = useState<LabAxis>("delta");
  const [showParts, setShowParts] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!name) return;
    api.snapshots(name).then((s) => { setSnaps(s); setSnapshot(s[0] ?? ""); });
  }, [name]);

  useEffect(() => {
    if (!snapshot) return;
    api.maturities(name, snapshot).then((m) => {
      setMats(m);
      setExpiry((prev) => nearestExpiry(m, prev || m[Math.min(4, m.length - 1)] || "") ?? "");
    });
  }, [name, snapshot]);

  useEffect(() => {
    if (!expiry || !mats.includes(expiry)) return;
    let live = true;
    api.smile(name, snapshot, expiry).then(
      (s) => { if (!live) return; setSmile(s); setP(fittedParams(s) ?? guessParams(s)); setError(""); },
      (e: Error) => live && setError(e.message),
    );
    return () => { live = false; };
  }, [name, snapshot, expiry, mats]);

  const fitted = smile ? fittedParams(smile) : null;
  const result = useMemo(() => (smile && p ? evaluate(smile, p, ax) : null), [smile, p, ax]);
  const fp = smile?.params;

  return (
    <>
      <div className="toolbar">
        <div className="field"><label className="field-label" htmlFor="lab-name">Underlying</label>
          <select id="lab-name" value={name} onChange={(e) => setName(e.target.value)}>
            {names.map((n) => <option key={n.name} value={n.name}>{n.name}</option>)}
          </select></div>
        <div className="field"><label className="field-label" htmlFor="lab-snap">Snapshot</label>
          <select id="lab-snap" value={snapshot} onChange={(e) => setSnapshot(e.target.value)}>
            {snaps.map((s) => <option key={s} value={s}>{fmtTs(s)}</option>)}
          </select></div>
        <div className="field"><label className="field-label" htmlFor="lab-exp">Expiry</label>
          <select id="lab-exp" value={expiry} onChange={(e) => setExpiry(e.target.value)}>
            {mats.map((m) => <option key={m} value={m}>{m}</option>)}
          </select></div>
        <div className="field"><span className="field-label">X axis</span>
          <Seg label="X axis" value={ax} options={AXES} onChange={setAx} /></div>
        <label className="lab-check"><input type="checkbox" checked={showParts} onChange={(e) => setShowParts(e.target.checked)} /> Show parts</label>
        <div className="toolbar-hint muted">
          σ = atm + skew·z + κ<sub>put</sub>·(z⁺)² + κ<sub>call</sub>·(z⁻)², z = Φ⁻¹(call Δ). Sliders only move the chart; nothing is saved.
        </div>
      </div>

      {error && <div className="note error">{error}</div>}
      {smile && p && result && (
        <div className="plots-layout">
          <div className="panel"><LabCharts points={result.points} p={p} ax={ax} showParts={showParts} /></div>
          <div className="side-stack">
            <ParamSliders p={p} fitted={fitted} stats={result.stats} onChange={setP}
              onReset={() => setP(fitted ?? guessParams(smile))} />
            <div className="panel">
              <div className="panel-head">Stored fit</div>
              <div className="panel-body">
                <table className="kv"><tbody>
                  <tr><td>Status</td><td>{fp?.fit_status ?? "not fitted"}</td></tr>
                  <tr><td>Inside (fitter)</td><td>{fp?.pct_inside == null ? "–" : `${(fp.pct_inside * 100).toFixed(1)}%`}</td></tr>
                  <tr><td>Quotes fitted</td><td>{fp?.n_fit_quotes ?? "–"}</td></tr>
                  <tr><td>Outliers</td><td>{fp?.n_outliers ?? "–"}</td></tr>
                  <tr><td>Forward</td><td>{fp?.forward == null ? "–" : fp.forward.toFixed(2)}</td></tr>
                </tbody></table>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
