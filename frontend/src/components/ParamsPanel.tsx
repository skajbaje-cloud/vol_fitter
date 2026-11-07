import { fmtNum, fmtPct, fmtTs } from "../lib/format";
import { hasFit } from "../lib/smile";
import type { SmileOut } from "../types";

function Rows({ rows }: { rows: [string, string][] }) {
  return (
    <table className="kv">
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}><td>{k}</td><td>{v}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

export function ParamsPanel({ smile }: { smile: SmileOut | undefined }) {
  const p = smile?.params;
  return (
    <>
      <div className="panel">
        <div className="panel-head">Snapshot &amp; forward — focused series</div>
        <div className="panel-body">
          {smile && p ? (
            <Rows rows={[
              ["underlying", smile.name],
              ["snapshot", fmtTs(smile.snapshot_ts)],
              ["expiry", smile.expiry],
              ["T (years)", fmtNum(smile.T, 4)],
              ["spot", fmtNum(smile.spot, 2)],
              ["forward", fmtNum(p.forward, 2)],
              ["discount factor", fmtNum(p.discount_factor, 5)],
              ["strikes used (F / DF)", `${p.n_strikes_forward ?? "—"} / ${p.n_strikes_df ?? "—"}`],
              ["LAD residual (F / DF)", `${fmtNum(p.forward_fit_resid, 3)} / ${fmtNum(p.df_fit_resid, 3)}`],
            ]} />
          ) : (
            <div className="muted">Click a series to see its parameters.</div>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">Smile fit — focused series</div>
        <div className="panel-body">
          {smile && p && hasFit(smile) ? (
            <Rows rows={[
              ["σ ATM", fmtPct(p.sigma_atm, 2)],
              ["skew", fmtNum(p.skew, 4)],
              ["κ call", fmtNum(p.kappa_call, 4)],
              ["κ put", fmtNum(p.kappa_put, 4)],
              ["fit RMSE", fmtNum(p.smile_fit_rmse, 4)],
              ["quality", p.smile_quality_flag ?? "—"],
            ]} />
          ) : (
            <div className="muted">Not fitted yet — per-expiry fitting is Phase 2.</div>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">Master params — underlying</div>
        <div className="panel-body muted">Not fitted yet — the cross-expiry master fit is Phase 3.</div>
      </div>
    </>
  );
}
