interface Props<T extends string> {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label?: string;
}

export function Seg<T extends string>({ value, options, onChange, label }: Props<T>) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={o.value === value ? "active" : ""}
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const X_OPTIONS = [
  { value: "delta" as const, label: "1 − call Δ" },
  { value: "strike" as const, label: "Strike" },
  { value: "moneyness" as const, label: "Moneyness" },
];
