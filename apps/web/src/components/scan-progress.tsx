"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { plural } from "@/lib/format";
import type { ScanEvent, ScanEventStatus } from "@/lib/types";

type StepState = "waiting" | "running" | "ok" | "failed" | "skipped" | "not-reached";
type Step = { key: string; group: string; label: string; state: StepState; detail: string; at: string | null };
type Connection = "connecting" | "open" | "reconnecting" | "stopped" | "ended";

const STATE: Record<ScanEventStatus, StepState> = { started: "running", ok: "ok", failed: "failed", skipped: "skipped" };

// Turns the event log into one row per step. The last event of a step decides its state.
function buildSteps(events: ScanEvent[], live: boolean): Step[] {
  const last = new Map<string, ScanEvent>();
  let findings: number | null = null;
  for (const event of events) {
    last.set(event.stage === "scanner" ? `scanner:${event.scanner}` : event.stage, event);
    if (event.stage === "triage" && event.status === "started") findings = event.count;
  }
  const missing: StepState = live ? "waiting" : "not-reached";

  const step = (key: string, group: string, label: string, describe: (e: ScanEvent) => string): Step => {
    const event = last.get(key);
    if (!event) return { key, group, label, state: missing, detail: live ? "Waiting" : "Not reached", at: null };
    return { key, group, label, state: STATE[event.status], detail: describe(event), at: event.at };
  };

  const scanners = [...last.keys()].filter((k) => k.startsWith("scanner:")).sort();
  return [
    step("checkout", "Checkout", "Fetch the commit", (e) => (e.status === "ok" ? "Read-only copy ready" : e.status === "failed" ? "Failed" : "Fetching")),
    step("plan", "Plan", "Choose the scanners", (e) => (e.count === null ? "Planning" : `${plural(e.count, "scanner")} to run`)),
    ...scanners.map((key) =>
      step(key, "Scan", key.slice("scanner:".length), (e) =>
        e.status === "ok"
          ? plural(e.count ?? 0, "finding")
          : e.status === "failed"
            ? "Failed, results may be missing"
            : e.status === "skipped"
              ? "Turned off in settings"
              : "Running",
      ),
    ),
    step("triage", "Triage", "Group and explain with AI", (e) =>
      e.status === "ok"
        ? `${plural(findings ?? 0, "finding")} → ${plural(e.count ?? 0, "issue")}`
        : e.status === "failed"
          ? "No usable AI answer"
          : `Reading ${plural(e.count ?? 0, "finding")}`,
    ),
    step("report", "Report", "Comment on the pull request", (e) =>
      e.status === "ok" ? `Posted, ${plural(e.count ?? 0, "issue")} shown` : e.status === "failed" ? "GitHub refused the comment" : "Posting"),
  ];
}

const DOT: Record<StepState, string> = {
  waiting: "border border-muted",
  running: "bg-ink animate-pulse",
  ok: "bg-signal",
  failed: "bg-sev-critical",
  skipped: "border border-muted",
  "not-reached": "border border-rule",
};

function offset(startedAt: string, at: string | null): string {
  if (!at) return "";
  const seconds = Math.max(0, Math.round((new Date(at).getTime() - new Date(startedAt).getTime()) / 1000));
  return seconds < 60 ? `+${seconds} s` : `+${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

const CONNECTION: Record<Connection, string> = {
  connecting: "Connecting",
  open: "Live",
  reconnecting: "Reconnecting",
  stopped: "Live updates stopped. Reload the page.",
  ended: "Finished, loading the results",
};

export function ScanProgress({
  scanId,
  startedAt,
  initialEvents,
  live,
}: {
  scanId: number;
  startedAt: string;
  initialEvents: ScanEvent[];
  live: boolean;
}) {
  const router = useRouter();
  const [events, setEvents] = useState(initialEvents);
  const [connection, setConnection] = useState<Connection>("connecting");

  useEffect(() => {
    if (!live) return;
    const source = new EventSource(`/dashboard/scans/${scanId}/events`);
    source.onopen = () => setConnection("open");
    source.addEventListener("progress", (message) => {
      const event = JSON.parse(message.data) as ScanEvent;
      setEvents((current) => (current.some((e) => e.id === event.id) ? current : [...current, event]));
    });
    source.addEventListener("end", () => {
      source.close();
      setConnection("ended");
      router.refresh();
    });
    // EventSource retries on its own after a dropped connection; CLOSED means it gave up (e.g. signed out).
    source.onerror = () => setConnection(source.readyState === EventSource.CLOSED ? "stopped" : "reconnecting");
    return () => source.close();
  }, [scanId, live, router]);

  const steps = buildSteps(events, live);

  return (
    <div>
      {live && (
        <p className="mb-3 inline-flex items-center gap-2 font-mono text-[12px] text-muted" role="status" aria-live="polite">
          <span
            className={`size-1.5 rounded-full ${connection === "open" ? "animate-pulse bg-signal" : connection === "stopped" ? "bg-sev-critical" : "bg-muted"}`}
            aria-hidden="true"
          />
          {CONNECTION[connection]}
        </p>
      )}
      <ol className="border-t border-ink">
        {steps.map((step, i) => (
          <li
            key={step.key}
            className={`grid grid-cols-[5.5rem_1fr_auto] items-baseline gap-x-4 border-b border-rule py-3 text-[14px] sm:grid-cols-[7rem_1fr_auto_4.5rem] ${
              step.state === "waiting" || step.state === "not-reached" ? "text-muted" : ""
            }`}
          >
            <span className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">
              {steps[i - 1]?.group === step.group ? "" : step.group}
            </span>
            <span className={step.group === "Scan" ? "font-mono text-[13px]" : ""}>{step.label}</span>
            <span className="inline-flex items-center gap-2 text-right text-[13px]">
              <span className={`size-1.5 shrink-0 rounded-full ${DOT[step.state]}`} aria-hidden="true" />
              <span className={step.state === "failed" ? "text-sev-critical" : step.state === "ok" ? "" : "text-muted"}>{step.detail}</span>
            </span>
            <span className="hidden text-right font-mono text-[12px] text-muted tabular-nums sm:block">{offset(startedAt, step.at)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
