import { useEffect, useRef, useState } from "react";

export interface MenuItem { label: string; onSelect: () => void; divider?: boolean }

/** "Select ▾" button: each entry ticks a preset set of rows once. It keeps no value of its own,
 *  so it can never show a stale choice after the rows are ticked by hand. */
export function SelectMenu({ items }: { items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    root.current?.querySelector<HTMLButtonElement>("[role=menuitem]")?.focus();
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  function onMenuKey(e: React.KeyboardEvent) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const btns = [...(root.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]") ?? [])];
    const i = btns.indexOf(document.activeElement as HTMLButtonElement);
    btns[(i + (e.key === "ArrowDown" ? 1 : btns.length - 1)) % btns.length]?.focus();
  }

  return (
    <div className="menu-wrap" ref={root}>
      <button type="button" className="btn-secondary" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Select <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="menu" role="menu" onKeyDown={onMenuKey}>
          {items.map((it) => (
            <button key={it.label} type="button" role="menuitem" className={it.divider ? "divider" : ""}
              onClick={() => { it.onSelect(); setOpen(false); }}>
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
