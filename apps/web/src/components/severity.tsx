import { SEVERITIES, type Severity } from "@/lib/types";

const COLOR: Record<Severity, string> = {
  critical: "bg-sev-critical",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
  low: "bg-sev-low",
  info: "bg-sev-info",
};

export function SeverityMark({ severity }: { severity: Severity }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-[0.06em] uppercase">
      <span className={`size-2 ${COLOR[severity]}`} aria-hidden="true" />
      {severity}
    </span>
  );
}

// "1 critical · 7 high · 3 medium" as small marks, most severe first.
export function SeverityCounts({ severities }: { severities: Severity[] }) {
  const counts = SEVERITIES.map((s) => [s, severities.filter((x) => x === s).length] as const).filter(([, n]) => n);
  if (counts.length === 0) return <span className="text-muted">No issues</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[12px] tabular-nums">
      {counts.map(([severity, n]) => (
        <span key={severity} className="inline-flex items-center gap-1.5" title={`${n} ${severity}`}>
          <span className={`size-2 ${COLOR[severity]}`} aria-hidden="true" />
          {n}
          <span className="sr-only">{severity}</span>
        </span>
      ))}
    </span>
  );
}
