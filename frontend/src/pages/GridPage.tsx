import { useEffect, useMemo, useState } from "react";
import { api, nearestExpiry } from "../api";
import { Plot, SERIES_COLORS, axis } from "../components/Plot";
import { Seg, X_OPTIONS } from "../components/Seg";
import { fmtNum, fmtTs } from "../lib/format";
import { bidAskPoints } from "../lib/smile";
import type { NameOut, SeriesSpec, SmileOut, XMode } from "../types";

type GridMode = "maturity" | "underlying";
interface Cell { key: string; title: string; smile: SmileOut }

function SmileCell({ cell, xMode, onOpen }: { cell: Cell; xMode: XMode; onOpen: () => void }) {
  const data = useMemo(() => {
    const { bid, ask } = bidAskPoints(cell.smile, xMode);
    const c = SERIES_COLORS[0];
    const t = (pts: typeof bid, symbol: string, name: string) => ({
      x: pts.map((p) => p.x), y: pts.map((p) => p.y), customdata: pts.map((p) => p.strike),
      mode: "markers", type: "scatter", name, marker: { color: c, size: 5, symbol, line: { color: c, width: 1 } },
      hovertemplate: `K %{customdata:,.0f}<br>IV %{y:.2%}<extra>${name}</extra>`,
    });
    return [t(bid, "triangle-down", "bid"), t(ask, "triangle-up-open", "ask")];
  }, [cell, xMode]);
  const layout = useMemo(() => ({
    margin: { l: 40, r: 8, t: 6, b: 26 }, showlegend: false, font: { size: 9.5, color: "#898781" },
    xaxis: axis(), yaxis: axis({ tickformat: ".0%" }),
  }), []);
  return (
    <div className="smile-cell">
      <button type="button" className="smile-cell-head mono" onClick={onOpen} title="Open in Plots">
        <span>{cell.title}</span>
        <span className="muted">F {fmtNum(cell.smile.params.forward, 1)} ↗</span>
      </button>
      <Plot data={data} layout={layout} height={200} />
    </div>
  );
}

interface Props {
  names: NameOut[];
  onOpenInPlots: (spec: Omit<SeriesSpec, "id" | "baseline">) => void;
}

export function GridPage({ names, onOpenInPlots }: Props) {
  const [mode, setMode] = useState<GridMode>("maturity");
  const [xMode, setXMode] = useState<XMode>("delta");
  const [name, setName] = useState(names[0]?.name ?? "");
  const [snaps, setSnaps] = useState<string[]>([]);
  const [snapshot, setSnapshot] = useState("");
  const [targets, setTargets] = useState<string[]>([]);
  const [target, setTarget] = useState("");
  const [cells, setCells] = useState<Cell[]>([]);
  const [status, setStatus] = useState("Loading…");

  useEffect(() => {
    if (!name) return;
    api.snapshots(name).then((s) => { setSnaps(s); setSnapshot(s[0] ?? ""); });
  }, [name]);

  // Underlying mode: every active name's latest snapshot, at the expiry nearest a chosen date.
  const active = useMemo(() => names.filter((n) => n.active), [names]);
  useEffect(() => {
    if (mode !== "underlying") return;
    Promise.all(active.map(async (n) => {
      const latest = (await api.snapshots(n.name))[0];
      return latest ? api.maturities(n.name, latest) : [];
    })).then((lists) => {
      const all = [...new Set(lists.flat())].sort();
      setTargets(all);
      setTarget((t) => t || all[1] || all[0] || "");
    });
  }, [mode, active]);

  useEffect(() => {
    let live = true;
    setStatus("Loading…");
    const load = async (): Promise<Cell[]> => {
      if (mode === "maturity") {
        if (!snapshot) return [];
        const mats = await api.maturities(name, snapshot);
        return Promise.all(mats.map(async (m) => ({ key: m, title: m, smile: await api.smile(name, snapshot, m) })));
      }
      if (!target) return [];
      const out = await Promise.all(active.map(async (n) => {
        const latest = (await api.snapshots(n.name))[0];
        const exp = latest && nearestExpiry(await api.maturities(n.name, latest), target);
        return latest && exp ? { key: n.name, title: `${n.name}  ${exp}`, smile: await api.smile(n.name, latest, exp) } : null;
      }));
      return out.filter((c): c is Cell => c !== null);
    };
    load().then(
      (c) => { if (live) { setCells(c); setStatus(c.length ? "" : "Nothing to show for this selection."); } },
      (e: Error) => live && setStatus(e.message),
    );
    return () => { live = false; };
  }, [mode, name, snapshot, target, active]);

  return (
    <>
      <div className="toolbar">
        <div className="field"><span className="field-label">Grid by</span>
          <Seg label="Grid by" value={mode} onChange={setMode} options={[
            { value: "maturity", label: "Maturity" }, { value: "underlying", label: "Underlying" },
          ]} />
        </div>
        {mode === "maturity" ? (
          <>
            <label className="field"><span className="field-label">Underlying</span>
              <select value={name} onChange={(e) => setName(e.target.value)}>
                {names.map((n) => <option key={n.name}>{n.name}</option>)}
              </select>
            </label>
            <label className="field"><span className="field-label">Snapshot</span>
              <select value={snapshot} onChange={(e) => setSnapshot(e.target.value)}>
                {snaps.map((s) => <option key={s} value={s}>{fmtTs(s)}</option>)}
              </select>
            </label>
          </>
        ) : (
          <label className="field"><span className="field-label">Expiry (nearest per name, latest snapshot)</span>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              {targets.map((t) => <option key={t}>{t}</option>)}
            </select>
          </label>
        )}
        <div className="field"><span className="field-label">X axis</span>
          <Seg label="X axis" value={xMode} options={X_OPTIONS} onChange={setXMode} />
        </div>
      </div>
      {status && <div className="muted empty">{status}</div>}
      <div className="smile-grid">
        {cells.map((c) => (
          <SmileCell key={c.key} cell={c} xMode={xMode} onOpen={() => onOpenInPlots({
            name: c.smile.name, snapshot: c.smile.snapshot_ts, expiry: c.smile.expiry, type: "bidask",
          })} />
        ))}
      </div>
    </>
  );
}
