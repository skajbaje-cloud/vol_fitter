interface Props {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  label: string;
  newestFirst?: boolean;          // options listed newest first (snapshots); ‹ always steps to the earlier date
}

/** A select with ‹ › buttons to step through dated options one at a time. */
export function StepSelect({ value, options, onChange, label, newestFirst }: Props) {
  const i = options.findIndex((o) => o.value === value);
  const at = (dir: -1 | 1) => options[i + (newestFirst ? -dir : dir)];
  const earlier = i >= 0 ? at(-1) : undefined, later = i >= 0 ? at(1) : undefined;
  return (
    <div className="step-select">
      <button type="button" className="btn-secondary" aria-label={`Earlier ${label}`} title={earlier?.label}
        disabled={!earlier} onClick={() => earlier && onChange(earlier.value)}>‹</button>
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <button type="button" className="btn-secondary" aria-label={`Later ${label}`} title={later?.label}
        disabled={!later} onClick={() => later && onChange(later.value)}>›</button>
    </div>
  );
}
