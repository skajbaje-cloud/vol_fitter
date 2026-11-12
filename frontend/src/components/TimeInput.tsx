import { useEffect, useState } from "react";

interface Props {
  value: string;                          // "HH:MM" or ""
  onChange: (v: string) => void;
  label: string;
  title?: string;
  disabled?: boolean;
  changed?: boolean;
}

/** "945", "0945", "9:45", "9.45" -> "09:45"; anything else is returned as typed (validation flags it). */
export function tidyTime(raw: string): string {
  const s = raw.trim();
  const m = /^(\d{1,2})[:.h]?(\d{2})$/.exec(s);
  if (!m) return s;
  const h = Number(m[1]), mi = Number(m[2]);
  return h < 24 && mi < 60 ? `${String(h).padStart(2, "0")}:${m[2]}` : s;
}

/** Always-24-hour time box. The browser's own time picker follows the OS locale and can show 12-hour times. */
export function TimeInput({ value, onChange, label, title, disabled, changed }: Props) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const commit = () => { const t = tidyTime(text); setText(t); if (t !== value) onChange(t); };

  return (
    <input type="text" inputMode="numeric" maxLength={5} placeholder="--:--" className={`sched-time ${changed ? "changed" : ""}`}
      value={text} disabled={disabled} title={title} aria-label={label}
      onChange={(e) => setText(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") commit(); }} />
  );
}
