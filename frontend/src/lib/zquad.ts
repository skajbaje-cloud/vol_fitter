// Client-side copy of the smile model (src/vol_fitter/smile/delta_smile.py):
//   sigma(z) = atm + skew*z + kappaPut*(z+)^2 + kappaCall*(z-)^2,  z = Phi^-1(forward call delta)
// plus the bid-ask fitter's "inside the spread" rule, so sliders can be judged live.
import type { SmileOut } from "../types";

export interface ZParams { atm: number; skew: number; kp: number; kc: number }
export type LabAxis = "delta" | "z";

export const PARAM_SPECS: { key: keyof ZParams; name: string; unit: string; min: number; max: number; step: number }[] = [
  { key: "atm", name: "ATM vol", unit: "σ at 50Δ", min: 0.05, max: 0.6, step: 0.0005 },
  { key: "skew", name: "Skew", unit: "per unit z", min: -0.15, max: 0.15, step: 0.0005 },
  { key: "kp", name: "Put kurtosis", unit: "extra vol at z = +1", min: -0.1, max: 0.2, step: 0.0002 },
  { key: "kc", name: "Call kurtosis", unit: "extra vol at z = −1", min: -0.1, max: 0.1, step: 0.0002 },
];

const CLIP = 1e-4;

/** Inverse standard normal CDF (Acklam). */
export function ppf(p: number): number {
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239];
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572];
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const tail = (q: number) => (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  if (p < 0.02425) return tail(Math.sqrt(-2 * Math.log(p)));
  if (p > 1 - 0.02425) return -tail(Math.sqrt(-2 * Math.log(1 - p)));
  const q = p - 0.5, r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}

export const zOf = (delta: number) => ppf(Math.min(Math.max(delta, CLIP), 1 - CLIP));

export function terms(p: ZParams, z: number) {
  const up = Math.max(z, 0), dn = Math.max(-z, 0);
  return { line: p.atm + p.skew * z, put: p.kp * up * up, call: p.kc * dn * dn };
}
export const volAtDelta = (p: ZParams, delta: number) => { const t = terms(p, zOf(delta)); return t.line + t.put + t.call; };

/** Chart x for a call delta: 1 − Δ (puts left), or Φ⁻¹(1 − Δ) = −z (same orientation, wings stretched). */
export const xOf = (axis: LabAxis, delta: number) => (axis === "delta" ? 1 - delta : -zOf(delta));

export function fittedParams(s: SmileOut): ZParams | null {
  const { sigma_atm, skew, kappa_put, kappa_call } = s.params;
  if (sigma_atm == null || skew == null || kappa_put == null || kappa_call == null) return null;
  return { atm: sigma_atm, skew, kp: kappa_put, kc: kappa_call };
}

/** Starting point for an unfitted expiry: atm and skew from near-the-money mids, no wings (as the fitter's guess). */
export function guessParams(s: SmileOut): ZParams {
  const pts: { z: number; mid: number }[] = [];
  s.quotes.fwd_delta.forEach((d, i) => {
    const b = s.quotes.bid_iv[i], a = s.quotes.ask_iv[i];
    if (d != null && b != null && a != null) pts.push({ z: zOf(d), mid: 0.5 * (a + b) });
  });
  const near = pts.filter((q) => Math.abs(q.z) < 0.25).map((q) => q.mid).sort((x, y) => x - y);
  const atm = near.length ? near[Math.floor(near.length / 2)] : 0.2;
  const band = pts.filter((q) => Math.abs(q.z) < 0.7);
  const mz = band.reduce((t, q) => t + q.z, 0) / (band.length || 1);
  const mm = band.reduce((t, q) => t + q.mid, 0) / (band.length || 1);
  const sxx = band.reduce((t, q) => t + (q.z - mz) ** 2, 0);
  const skew = band.length >= 3 && sxx > 0 ? band.reduce((t, q) => t + (q.z - mz) * (q.mid - mm), 0) / sxx : 0;
  return { atm, skew, kp: 0, kc: 0 };
}

export interface LabPoint {
  x: number; strike: number; isCall: boolean;
  bid: number | null; ask: number | null; model: number; inside: boolean;
  resid: number | null; half: number | null;   // two-sided only: model − mid and the floored half-spread
}
export interface LabStats { n: number; inside: number; withinHalf: number; medMissBp: number; maxMissVolPts: number }

/** Every usable quote judged against the model with the fitter's rule (half-spread floored at h_min). */
export function evaluate(s: SmileOut, p: ZParams, axis: LabAxis): { points: LabPoint[]; stats: LabStats } {
  const q = s.quotes, points: LabPoint[] = [], misses: number[] = [];
  let inside = 0, withinHalf = 0, maxMiss = 0;
  q.fwd_delta.forEach((d, i) => {
    const b = q.bid_iv[i], a = q.ask_iv[i];
    if (d == null || (b == null && a == null)) return;
    const sig = volAtDelta(p, d);
    let viol = 0, resid: number | null = null, half: number | null = null;
    if (b != null && a != null) {
      half = Math.max(0.5 * (a - b), s.h_min);
      resid = sig - 0.5 * (a + b);
      viol = Math.max(Math.abs(resid) - half, 0);
      if (viol < half) withinHalf++;
    } else {
      viol = a != null ? Math.max(sig - a, 0) : Math.max((b as number) - sig, 0);
      if (viol < s.h_min) withinHalf++;
    }
    const ok = viol <= 1e-9;
    if (ok) inside++; else misses.push(viol);
    maxMiss = Math.max(maxMiss, viol);
    points.push({ x: xOf(axis, d), strike: q.strike[i], isCall: q.is_call[i], bid: b, ask: a, model: sig, inside: ok, resid, half });
  });
  misses.sort((x, y) => x - y);
  const n = points.length;
  return {
    points,
    stats: {
      n, inside: n ? inside / n : 0, withinHalf: n ? withinHalf / n : 0,
      medMissBp: misses.length ? misses[Math.floor(misses.length / 2)] * 1e4 : 0, maxMissVolPts: maxMiss * 100,
    },
  };
}
