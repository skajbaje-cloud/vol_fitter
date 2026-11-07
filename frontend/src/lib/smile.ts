import type { SmileOut, XMode } from "../types";

export interface Pt {
  x: number;
  y: number;
  strike: number;
  isCall: boolean;
}

export const X_LABELS: Record<XMode, string> = {
  delta: "1 − call Δ equivalent",
  strike: "Strike",
  moneyness: "Moneyness (K / F)",
};

function forwardOf(s: SmileOut): number {
  return s.params.forward ?? s.spot ?? 1;
}

function xOf(mode: XMode, strike: number, isCall: boolean, delta: number, forward: number): number {
  if (mode === "strike") return strike;
  if (mode === "moneyness") return strike / forward;
  const callDeltaEquiv = isCall ? delta : 1 + delta;
  return 1 - callDeltaEquiv;
}

/** Bid and ask IV points for every two-sided quote, calls and puts together. */
export function bidAskPoints(s: SmileOut, mode: XMode): { bid: Pt[]; ask: Pt[] } {
  const q = s.quotes;
  const F = forwardOf(s);
  const bid: Pt[] = [];
  const ask: Pt[] = [];
  for (let i = 0; i < q.strike.length; i++) {
    // A missing side means no real market (e.g. a far-OTM strike with only a floor-tick ask).
    if (q.bid[i] == null || q.ask[i] == null) continue;
    const [k, c] = [q.strike[i], q.is_call[i]];
    const [bIv, aIv, bD, aD] = [q.bid_iv[i], q.ask_iv[i], q.bid_delta[i], q.ask_delta[i]];
    if (bIv != null && bD != null) bid.push({ x: xOf(mode, k, c, bD, F), y: bIv, strike: k, isCall: c });
    if (aIv != null && aD != null) ask.push({ x: xOf(mode, k, c, aD, F), y: aIv, strike: k, isCall: c });
  }
  return { bid, ask };
}

/** One mid-IV point per strike from the out-of-the-money option (puts below F, calls above). */
export function midCurve(s: SmileOut, mode: XMode): Pt[] {
  const q = s.quotes;
  const F = forwardOf(s);
  const out: Pt[] = [];
  for (let i = 0; i < q.strike.length; i++) {
    const [k, c] = [q.strike[i], q.is_call[i]];
    if (c !== k >= F || q.bid[i] == null || q.ask[i] == null) continue;
    const [bIv, aIv, bD, aD] = [q.bid_iv[i], q.ask_iv[i], q.bid_delta[i], q.ask_delta[i]];
    if (bIv == null || aIv == null || bD == null || aD == null) continue;
    out.push({ x: xOf(mode, k, c, (bD + aD) / 2, F), y: (bIv + aIv) / 2, strike: k, isCall: c });
  }
  return out.sort((a, b) => a.x - b.x);
}

/** Linear interpolation on a curve sorted by x; null outside its range. */
export function interp(curve: Pt[], x: number): number | null {
  if (curve.length < 2 || x < curve[0].x || x > curve[curve.length - 1].x) return null;
  for (let i = 0; i < curve.length - 1; i++) {
    const [a, b] = [curve[i], curve[i + 1]];
    if (x <= b.x) return b.x === a.x ? a.y : a.y + ((x - a.x) / (b.x - a.x)) * (b.y - a.y);
  }
  return null;
}

export function hasFit(s: SmileOut): boolean {
  return s.params.sigma_atm != null;
}
