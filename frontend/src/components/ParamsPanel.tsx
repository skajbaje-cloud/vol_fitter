import { fmtNum, fmtPct, fmtTs } from "../lib/format";
import { hasFit } from "../lib/smile";
import type { SmileOut } from "../types";

/** The focused series' smile: where it was snapped, its forward, and its stored fit (if any). */
export function ParamsPanel({ smile }: { smile: SmileOut | undefined }) {
  const p = smile?.params;
  const fit = smile && hasFit(smile);
  const rows: [string, string][] = smile && p ? [
    ["snapshot", fmtTs(smile.snapshot_ts)],
    ["T (years)", fmtNum(smile.T, 4)],
    ["spot · forward", `${fmtNum(smile.spot, 2)} · ${fmtNum(p.forward, 2)}`],
    ["discount factor", fmtNum(p.discount_factor, 5)],
    ...(fit ? [
      ["σ ATM", fmtPct(p.sigma_atm, 2)],
      ["skew", fmtNum(p.skew, 4)],
      ["κ put · κ call", `${fmtNum(p.kappa_put, 4)} · ${fmtNum(p.kappa_call, 4)}`],
      ["inside", fmtPct(p.pct_inside, 0)],
    ] as [string, string][] : [["fit", "not fitted"] as [string, string]]),
  ] : [];

  return (
    <div className="panel">
      <div className="panel-head">{smile ? `${smile.name} ${smile.expiry}` : "Focused series"}</div>
      <div className="panel-body">
        {rows.length ? (
          <table className="kv"><tbody>
            {rows.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}
          </tbody></table>
        ) : <div className="muted">Click a series to see its parameters.</div>}
      </div>
    </div>
  );
}
