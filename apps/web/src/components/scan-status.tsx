import type { ScanStatus } from "@/lib/types";

const LABEL: Record<ScanStatus, string> = { running: "Running", done: "Done", failed: "Failed" };

const DOT: Record<ScanStatus, string> = {
  running: "bg-muted animate-pulse",
  done: "bg-signal",
  failed: "bg-sev-critical",
};

export function ScanStatusBadge({ status, incomplete = false }: { status: ScanStatus; incomplete?: boolean }) {
  const label = status === "done" && incomplete ? "Incomplete" : LABEL[status];
  const dot = status === "done" && incomplete ? "bg-sev-medium" : DOT[status];
  return (
    <span className="inline-flex items-center gap-2 text-[13px]">
      <span className={`size-1.5 rounded-full ${dot}`} aria-hidden="true" />
      {label}
    </span>
  );
}
