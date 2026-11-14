import type {
  ExpiryFit, FitCoverage, FitMode, JobOut, NameIn, NameOut, NamePatch, ScheduleItemIn, ScheduleOut, SchedulerStatus,
  SmileOut, SplineExpiry,
} from "./types";

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

const post = <T>(url: string, body: unknown, method = "POST") =>
  request<T>(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  names: () => request<NameOut[]>("api/names"),
  snapshots: (name: string) => request<string[]>(`api/names/${enc(name)}/snapshots`),
  maturities: (name: string, snapshot: string) =>
    cached<string[]>(`api/names/${enc(name)}/snapshots/${enc(snapshot)}/maturities`),
  smile: (name: string, snapshot: string, expiry: string) =>
    cached<SmileOut>(`api/smile?${new URLSearchParams({ name, snapshot_ts: snapshot, expiry })}`),
  jobs: () => request<JobOut[]>("api/jobs"),
  job: (id: number) => request<JobOut>(`api/jobs/${id}`),
  runSnapshots: (names: string[]) => post<JobOut[]>("api/snapshots/run", { names }),
  registerNames: (body: NameIn[]) => post<NameOut[]>("api/names", body),
  patchName: (name: string, patch: NamePatch) => post<NameOut>(`api/names/${enc(name)}`, patch, "PATCH"),
  lookup: (rics: string[]) => post<JobOut>("api/names/lookup", { rics }),
  checkChain: (name: string, chain_ric: string) => post<JobOut>("api/names/check", { name, chain_ric }),
  schedule: () => request<ScheduleOut>("api/schedule"),
  saveSchedule: (items: ScheduleItemIn[]) => post<ScheduleOut>("api/schedule", { items }, "PUT"),
  schedulerStatus: () => request<SchedulerStatus>("api/scheduler/status"),
  pauseScheduler: (paused: boolean) => post<SchedulerStatus>("api/scheduler/pause", { paused }),
  runFits: (names: string[], mode: FitMode, anchor: boolean, snapshot_ts?: string) =>
    post<JobOut[]>("api/fits/run", { names, mode, anchor, snapshot_ts }),
  fitCoverage: () => request<FitCoverage[]>("api/fits/coverage"),
  /** Not cached: the model overlay changes on a refit (the server caches the spline fits themselves). */
  splineStudy: (name: string, snapshot: string) => request<SplineExpiry[]>(`api/spline/${enc(name)}/${enc(snapshot)}`),
  expiryFits: (name: string, snapshot: string) => request<ExpiryFit[]>(`api/fits/${enc(name)}/${enc(snapshot)}`),
  /** A fit rewrites a snapshot's params, so cached smiles (which carry them) must be re-read. */
  forgetSmiles: () => { for (const k of [...cache.keys()]) if (k.startsWith("api/smile?")) cache.delete(k); },
};

export function nearestExpiry(expiries: string[], target: string): string | undefined {
  const t = Date.parse(target);
  return [...expiries].sort((a, b) => Math.abs(Date.parse(a) - t) - Math.abs(Date.parse(b) - t))[0];
}
