import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

const level = (line: string) => (/ (ERROR|CRITICAL) /.test(line) ? "error-text" : / WARNING /.test(line) ? "warn-text" : "");

/** Recent server log lines (kept in memory on the server, cleared on restart). Refresh on demand only. */
export function LogsPage() {
  const [lines, setLines] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const box = useRef<HTMLPreElement>(null);

  const load = useCallback(() => {
    setError("");
    api.logs().then(setLines, (e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [lines]);

  return (
    <div className="panel">
      <div className="names-bar">
        <span className="muted">{lines ? `${lines.length} lines, newest at the bottom` : "Loading…"}</span>
        <span className="spacer" />
        {error && <span className="error-text">{error}</span>}
        <button type="button" className="btn-secondary" onClick={load}>Refresh</button>
      </div>
      <pre ref={box} className="log-box mono">
        {lines?.length === 0 && <span className="muted">Nothing logged since the server started.</span>}
        {lines?.map((l, i) => <div key={i} className={level(l)}>{l}</div>)}
      </pre>
    </div>
  );
}
