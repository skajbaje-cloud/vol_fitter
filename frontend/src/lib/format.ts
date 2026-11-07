export const fmtTs = (ts: string | null | undefined) => (ts ? ts.replace("T", " ").slice(0, 19) : "—");

export const fmtTime = (ts: string | null | undefined) => (ts ? ts.replace("T", " ").slice(11, 19) : "—");

export function fmtNum(v: number | null | undefined, digits = 2): string {
  return v == null ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export const fmtPct = (v: number | null | undefined, digits = 1) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);

export const seriesLabel = (s: { name: string; expiry: string; snapshot: string }) =>
  `${s.name} ${s.expiry} · ${fmtTs(s.snapshot).slice(5, 16)}`;
