import Link from "next/link";

import { requestFix } from "@/app/dashboard/scans/actions";
import { SubmitButton } from "@/components/submit-button";
import type { FixRequest, Issue } from "@/lib/types";

const BUTTON =
  "inline-flex h-9 items-center justify-center rounded-[4px] border border-ink/20 bg-surface px-4 text-[13px] font-medium transition-colors hover:border-ink/50";

// The same rules as the database policy, so the page never offers a button the database would refuse.
export function whyNotFixable(issue: Issue): string | null {
  if (issue.findings.some((f) => f.tool === "gitleaks")) return "Leaked secrets are not fixed automatically: rotate the secret first.";
  if (issue.false_positive) return "The AI marked this as a false positive, so there is nothing to patch.";
  return null;
}

// What the person sees under an issue: a button, the worker's progress, or the fix waiting for them.
// Only fixed sentences: nothing here is written by a model.
export function FixPanel({ scanId, issue, request }: { scanId: number; issue: Issue; request: FixRequest | undefined }) {
  const blocked = whyNotFixable(issue);
  if (blocked) return <Line tone="muted">{blocked}</Line>;

  if (!request) {
    return (
      <Form scanId={scanId} issueId={issue.id}>
        <p className="text-[13px] text-muted">A model drafts a patch, the sandbox re-scans it, then it waits for you.</p>
        <SubmitButton className={BUTTON} pending="Requesting…">
          Request a fix
        </SubmitButton>
      </Form>
    );
  }

  switch (request.status) {
    case "queued":
      return <Line tone="busy">Fix requested. Waiting for the worker to pick it up.</Line>;
    case "working":
      return <Line tone="busy">Drafting a patch and testing it in the sandbox. This takes a minute or two.</Line>;
    case "waiting":
      return <Proposed request={request} />;
    case "refused":
      return <Line tone="muted">Sentinel refused to patch this automatically. It needs a person.</Line>;
    case "no_fix":
      return <Retry scanId={scanId} issueId={issue.id}>The model found no safe change for this issue.</Retry>;
    case "not_verified":
      return <Retry scanId={scanId} issueId={issue.id}>The draft did not pass the sandbox re-scan, so it was thrown away.</Retry>;
    case "failed":
      return <Retry scanId={scanId} issueId={issue.id}>The fix could not be made (AI quota or GitHub). Nothing was changed.</Retry>;
  }
}

function Proposed({ request }: { request: FixRequest }) {
  const href = `/dashboard/fixes/${request.fix_id}`;
  const link = (label: string) => (
    <Link href={href} className="underline decoration-rule underline-offset-4 hover:decoration-ink">
      {label}
    </Link>
  );
  const status = request.fix?.status ?? "waiting";
  if (status === "approved") {
    return (
      <Line tone="ok">
        Fix approved. {request.fix?.pr_url ? link("See the fix pull request") : link("See the fix")}.
      </Line>
    );
  }
  if (status === "rejected") return <Line tone="muted">You rejected the proposed fix. {link("See it")}.</Line>;
  if (status === "outdated") return <Line tone="muted">The pull request moved on before the fix was applied. {link("See it")}.</Line>;
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
      <Line tone="ok">A verified patch is ready.</Line>
      <Link href={href} className="inline-flex h-9 items-center rounded-[4px] bg-ink px-4 text-[13px] font-medium text-paper transition-opacity hover:opacity-85">
        Review the fix
      </Link>
    </div>
  );
}

function Retry({ scanId, issueId, children }: { scanId: number; issueId: number; children: React.ReactNode }) {
  return (
    <Form scanId={scanId} issueId={issueId} retry>
      <p className="text-[13px] text-muted">{children}</p>
      <SubmitButton className={BUTTON} pending="Requesting…">
        Try again
      </SubmitButton>
    </Form>
  );
}

function Form({ scanId, issueId, retry, children }: { scanId: number; issueId: number; retry?: boolean; children: React.ReactNode }) {
  return (
    <form action={requestFix} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
      <input type="hidden" name="scan_id" value={scanId} />
      <input type="hidden" name="issue_id" value={issueId} />
      {retry && <input type="hidden" name="retry" value="1" />}
      {children}
    </form>
  );
}

const DOT = { busy: "bg-ink animate-pulse", ok: "bg-signal", muted: "border border-muted" } as const;

function Line({ tone, children }: { tone: keyof typeof DOT; children: React.ReactNode }) {
  return (
    <p className={`inline-flex items-center gap-2.5 text-[13px] ${tone === "muted" ? "text-muted" : ""}`} role={tone === "busy" ? "status" : undefined}>
      <span className={`size-1.5 shrink-0 rounded-full ${DOT[tone]}`} aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}
