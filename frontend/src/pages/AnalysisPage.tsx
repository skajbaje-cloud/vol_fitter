const PLANNED = [
  ["Parameter history", "σ ATM, skew and the two wing κ's for one underlying and expiry, across snapshots."],
  ["Fit quality", "RMSE and quality flag for every underlying × expiry, sorted so the worst fits surface first."],
  ["Residuals", "Actual minus fitted IV against delta — already reachable from Plots in Difference mode once fits exist."],
  ["Cross-name comparison", "Master parameters (vol level, term structure, skew, wings) ranked across underlyings."],
];

export function AnalysisPage() {
  return (
    <>
      <div className="phase-banner">Fit analysis depends on Phase 2/3 fit output, which doesn't exist yet. Planned views:</div>
      <div className="planned-grid">
        {PLANNED.map(([title, body]) => (
          <div key={title} className="panel">
            <div className="panel-head">{title}</div>
            <div className="panel-body muted">{body}</div>
          </div>
        ))}
      </div>
    </>
  );
}
