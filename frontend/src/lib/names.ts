// Client-side state for the Snapshot tab's names table: names typed in but not yet registered,
// and the keys used to tick rows (pending and registered rows share one selection).
import type { ChainCheck, ExpiryFilter, NameLookup } from "../types";

export const RIC_RE = /^[A-Za-z0-9.^=_\-]{1,32}$/;      // mirrors web/schemas_names.py
export const CHAIN_RE = /^[A-Za-z0-9.^=_\-#*+:]{1,64}$/;

export interface PendingName {
  ric: string;
  lookupJob: number | null;
  lookup: NameLookup | null;      // null while LSEG is being asked
  lookupError: string;
  chain: string;
  display_name: string;
  group_name: string;
  expiry_filter: ExpiryFilter;
  active: boolean;
  timezone: string;               // IANA zone; pre-filled from the look-up's guess
}

export type PendingState = "looking" | "notfound" | "choose" | "ready";

export const pendingKey = (ric: string) => `p:${ric}`;
export const nameKey = (name: string) => `n:${name}`;

/** Split pasted text on commas, spaces or new lines; keep order, drop repeats. */
export function parseRics(text: string): { rics: string[]; bad: string[] } {
  const parts = [...new Set(text.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean))];
  return { rics: parts.filter((r) => RIC_RE.test(r)), bad: parts.filter((r) => !RIC_RE.test(r)) };
}

export function newPending(ric: string, lookupJob: number | null): PendingName {
  return {
    ric, lookupJob, lookup: null, lookupError: "", chain: "", display_name: "", group_name: "",
    expiry_filter: "all", active: true, timezone: "",
  };
}

export function applyLookup(p: PendingName, l: NameLookup): PendingName {
  const best = l.candidates.find((c) => c.preferred);
  return {
    ...p, lookup: l, chain: p.chain || best?.chain_ric || "", display_name: p.display_name || l.display_name || "",
    timezone: p.timezone || l.timezone_guess || "",
  };
}

export function pendingState(p: PendingName): PendingState {
  if (p.lookupError || (p.lookup && !p.lookup.found)) return "notfound";
  if (!p.lookup) return "looking";
  return CHAIN_RE.test(p.chain) ? "ready" : "choose";
}

export const isToday = (ts: string | null) => !!ts && ts.slice(0, 10) === new Date().toLocaleDateString("en-CA");

export function checkSummary(c: ChainCheck): string {
  const range = c.last_expiry ? ` · to ${c.last_expiry.slice(0, 7)}` : "";
  return `${c.n_options.toLocaleString()} options · ${c.n_expiries} expiries${range}`;
}
