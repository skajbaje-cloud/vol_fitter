import type { JobOut, NameOut, SmileOut } from "./types";

// Relative URLs: the page is always served from the same origin as the API
// (FastAPI in prod/tunnel, Vite's /api proxy in dev), so nothing is hardcoded.
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

// A snapshot's maturities and smiles never change once written, so cache them.
const cache = new Map<string, Promise<unknown>>();
function cached<T>(url: string): Promise<T> {
  let p = cache.get(url) as Promise<T> | undefined;
  if (!p) {
    p = request<T>(url);
    cache.set(url, p);
    p.catch(() => cache.delete(url));
  }
  return p;
}

const enc = encodeURIComponent;

export const api = {
  names: () => request<NameOut[]>("api/names"),
  snapshots: (name: string) => request<string[]>(`api/names/${enc(name)}/snapshots`),
  maturities: (name: string, snapshot: string) =>
    cached<string[]>(`api/names/${enc(name)}/snapshots/${enc(snapshot)}/maturities`),
  smile: (name: string, snapshot: string, expiry: string) =>
    cached<SmileOut>(`api/smile?${new URLSearchParams({ name, snapshot_ts: snapshot, expiry })}`),
  jobs: () => request<JobOut[]>("api/jobs"),
  runSnapshot: (body: { scope: "single" | "universe"; underlying?: string; chain_ric?: string }) =>
    request<JobOut[]>("api/snapshots/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};

export function nearestExpiry(expiries: string[], target: string): string | undefined {
  const t = Date.parse(target);
  return [...expiries].sort((a, b) => Math.abs(Date.parse(a) - t) - Math.abs(Date.parse(b) - t))[0];
}
