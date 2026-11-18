import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { fmtTs } from "./lib/format";
import { LabPage } from "./pages/LabPage";
import { LogsPage } from "./pages/LogsPage";
import { PlotsPage } from "./pages/PlotsPage";
import { UnderlyingsPage } from "./pages/UnderlyingsPage";
import type { NameOut, Route, SeriesSpec } from "./types";

const icon = (d: string) => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d={d} /></svg>
);
const NAV: { route: Route; label: string; icon: ReactNode }[] = [
  { route: "plots", label: "Plots", icon: icon("M3 17l6-6 4 4 8-8M15 7h6v6") },
  { route: "lab", label: "Lab", icon: icon("M4 6h16M4 12h16M4 18h16M9 4v4M15 10v4M7 16v4") },
  { route: "underlyings", label: "Underlyings", icon: icon("M3 5h18M3 12h18M3 19h18M8 5v14") },
  { route: "logs", label: "Logs", icon: icon("M5 4h14v16H5zM8 8h8M8 12h8M8 16h5") },
];
const ROUTES = NAV.map((n) => n.route);
const routeFromHash = (): Route => (ROUTES.includes(location.hash.slice(1) as Route) ? (location.hash.slice(1) as Route) : "plots");

async function defaultSeries(names: NameOut[]): Promise<SeriesSpec[]> {
  for (const n of names) {
    const snapshot = (await api.snapshots(n.name))[0];
    if (!snapshot) continue;
    const mats = await api.maturities(n.name, snapshot);
    return [{ id: 1, name: n.name, snapshot, expiry: mats[1] ?? mats[0], type: "bidask", baseline: true }];
  }
  return [];
}

export function App() {
  const [route, setRoute] = useState<Route>(routeFromHash);
  const [visited, setVisited] = useState<Set<Route>>(() => new Set([routeFromHash()]));
  const [names, setNames] = useState<NameOut[] | null>(null);
  const [latest, setLatest] = useState<{ name: string; ts: string } | null>(null);
  const [series, setSeries] = useState<SeriesSpec[] | null>(null);
  const updateSeries = useCallback((u: (prev: SeriesSpec[]) => SeriesSpec[]) => setSeries((prev) => u(prev ?? [])), []);
  const [error, setError] = useState("");
  const [plotsResetKey, setPlotsResetKey] = useState(0);

  const loadNames = useCallback(async () => {
    try {
      const all = await api.names();
      setNames(all);
      const stamps = all.filter((x) => x.last_snapshot_ts).map((x) => ({ name: x.name, ts: x.last_snapshot_ts! }));
      setLatest(stamps.sort((a, b) => b.ts.localeCompare(a.ts))[0] ?? null);
      return all.filter((x) => x.last_snapshot_ts);
    } catch (e) {
      setError(`Can't reach the API: ${(e as Error).message}`);
      return null;
    }
  }, []);

  useEffect(() => {
    loadNames().then(async (n) => n && setSeries(await defaultSeries(n)));
  }, [loadNames]);

  useEffect(() => {
    const onHash = () => {
      const r = routeFromHash();
      setRoute(r);
      setVisited((v) => new Set(v).add(r));
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const refreshAfterRun = useCallback(async () => {
    const n = await loadNames();
    if (n) {
      const fresh = await defaultSeries(n);
      setSeries((prev) => (prev && prev.length ? prev : fresh));
    }
  }, [loadNames]);

  const openInPlots = useCallback((spec: Omit<SeriesSpec, "id" | "baseline">) => {
    setSeries([{ ...spec, id: 1, baseline: true }]);
    setPlotsResetKey((k) => k + 1);
    location.hash = "plots";
  }, []);

  // Only names with priced data are worth offering on the analysis pages; Snapshot manages them all.
  const snapped = useMemo(() => (names ?? []).filter((n) => n.last_snapshot_ts), [names]);
  const pages: Record<Route, () => ReactNode> = {
    plots: () => (series === null ? <div className="muted empty">Loading…</div>
      : series.length ? <PlotsPage names={snapped} series={series} setSeries={updateSeries} resetKey={plotsResetKey} onOpenInPlots={openInPlots} />
      : <div className="muted empty">No priced snapshots yet. Take one from the Underlyings tab.</div>),
    lab: () => (snapped.length ? <LabPage names={snapped} active={route === "lab"} onOpenInPlots={openInPlots} />
      : <div className="muted empty">No priced snapshots yet. Take one from the Underlyings tab.</div>),
    underlyings: () => <UnderlyingsPage names={names!} onNamesChanged={refreshAfterRun} onOpenInPlots={openInPlots} />,
    logs: () => <LogsPage />,
  };

  return (
    <div className="shell">
      <nav className="rail" aria-label="Sections">
        <div className="brand"><span className="dot" /> vol_fitter</div>
        {NAV.map((n) => (
          <a key={n.route} href={`#${n.route}`} className={`nav-item${route === n.route ? " active" : ""}`}
            aria-current={route === n.route ? "page" : undefined}>
            {n.icon}{n.label}
          </a>
        ))}
        {latest && (
          <div className="rail-status mono" title={`Latest snapshot: ${latest.name} ${fmtTs(latest.ts)}`}>
            <span className="led" />{names?.length ?? 0} name{names?.length === 1 ? "" : "s"}<br />
            latest {latest.name}<br />{fmtTs(latest.ts).slice(5, 16)}
          </div>
        )}
      </nav>

      <main className="main">
        {error && <div className="note error">{error}</div>}
        {!names && !error && <div className="muted empty">Loading…</div>}
        {names && ROUTES.filter((r) => visited.has(r)).map((r) => (
          <section key={r} className="page" hidden={r !== route}>{pages[r]()}</section>
        ))}
      </main>
    </div>
  );
}
