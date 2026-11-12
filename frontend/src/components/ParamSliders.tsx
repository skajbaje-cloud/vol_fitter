import { PARAM_SPECS, type LabStats, type ZParams } from "../lib/zquad";

interface Props {
  p: ZParams;
  fitted: ZParams | null;        // stored fit for this expiry, if any
  stats: LabStats;
  onChange: (p: ZParams) => void;
  onReset: () => void;
}

export function ParamSliders({ p, fitted, stats, onChange, onReset }: Props) {
  return (
    <div className="panel">
      <div className="panel-head">Parameters</div>
      <div className="panel-body lab-params">
        {PARAM_SPECS.map((s) => (
          <div key={s.key} className="lab-param">
            <div className="lab-param-top">
              <label htmlFor={`lab-${s.key}`}>{s.name} <span className="muted">{s.unit}</span></label>
              <span className="mono">{p[s.key].toFixed(4)}</span>
            </div>
            <input id={`lab-${s.key}`} type="range" min={s.min} max={s.max} step={s.step} value={p[s.key]}
              onChange={(e) => onChange({ ...p, [s.key]: +e.target.value })} />
            <span className="mono muted lab-fit">{fitted ? `fit ${fitted[s.key].toFixed(4)}` : "not fitted yet"}</span>
          </div>
        ))}
        <button type="button" className="chip" onClick={onReset}>
          {fitted ? "Reset to fitted values" : "Reset to starting guess"}
        </button>
      </div>
      <div className="lab-stats">
        <div className={stats.inside < 0.5 ? "bad" : ""}><b className="mono">{Math.round(stats.inside * 100)}%</b><span>quotes inside</span></div>
        <div><b className="mono">{Math.round(stats.withinHalf * 100)}%</b><span>within one half-spread</span></div>
        <div><b className="mono">{stats.medMissBp.toFixed(1)}</b><span>median miss (bp of vol)</span></div>
        <div><b className="mono">{stats.maxMissVolPts.toFixed(2)}</b><span>worst miss (vol pts)</span></div>
      </div>
    </div>
  );
}
