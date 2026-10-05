import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { decide } from "@/app/dashboard/fixes/actions";
import { AiText } from "@/components/ai-text";
import { AutoRefresh } from "@/components/auto-refresh";
import { DiffView } from "@/components/diff-view";
import { PageIntro, Section } from "@/components/page-intro";
import { SubmitButton } from "@/components/submit-button";
import { getApproval, getFix, getFixScanId, isFixId } from "@/lib/data";
import { formatDateTime, formatRelative, shortSha } from "@/lib/format";
import type { Approval, Fix } from "@/lib/types";

export const metadata: Metadata = { title: "Review a fix · Sentinel" };

const ERRORS: Record<string, string> = {
  decided: "A decision was already recorded for this fix.",
  closed: "This fix is no longer waiting for a decision.",
  invalid: "The decision was not valid. Reload the page and try again.",
  failed: "The decision could not be saved. Try again.",
};

export default async function FixPage({ params, searchParams }: PageProps<"/dashboard/fixes/[id]">) {
  const { id } = await params;
  const fix = isFixId(id) ? await getFix(id) : null;
  if (!fix) notFound();
  const [approval, scanId] = await Promise.all([getApproval(fix.id), getFixScanId(fix.id)]);
  const { error } = await searchParams;
  const message = typeof error === "string" ? ERRORS[error] : undefined;
  const github = `https://github.com/${fix.repo.full_name}`;

  return (
    <>
      <PageIntro
        label="Proposed fix"
        crumbs={[
          { href: "/dashboard", label: "Overview" },
          { href: `/dashboard/repos/${fix.repo.id}`, label: fix.repo.full_name },
          ...(scanId ? [{ href: `/dashboard/scans/${scanId}`, label: `Scan ${scanId}` }] : []),
        ]}
      >
        <h1 className="font-serif text-[36px] leading-[1.08] tracking-[-0.02em] text-balance [overflow-wrap:anywhere]">{fix.issue_title}</h1>
        <p className="mt-3 text-muted">
          For{" "}
          <a href={`${github}/pull/${fix.pr}`} rel="noreferrer" target="_blank" className="underline decoration-rule underline-offset-4 hover:text-ink">
            pull request #{fix.pr}
          </a>{" "}
          at <span className="font-mono text-[13px]">{shortSha(fix.head_sha)}</span> · drafted by {fix.provider} ·{" "}
          <span title={formatDateTime(fix.created_at)}>{formatRelative(fix.created_at)}</span>
        </p>

        <dl className="mt-8 grid grid-cols-2 border-t border-ink sm:grid-cols-3">
          <Fact term="Sandbox">
            <span className="inline-flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-signal" aria-hidden="true" />
              Verified
            </span>
          </Fact>
          <Fact term="Re-scanned with">{fix.scanners.join(", ") || "—"}</Fact>
          <Fact term="Patch">
            <span className="font-mono">{fix.patch_id}</span>
          </Fact>
        </dl>

        <div className="mt-6 border-l-2 border-rule pl-4">
          <p className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">What the model says it changed</p>
          <AiText text={fix.summary} className="mt-1.5 text-[15px]" />
        </div>
      </PageIntro>

      <Section title="The change" aside="Read every line: this is exactly what would be committed.">
        <DiffView diff={fix.diff} />
      </Section>

      <Section title="Decision">
        {message && (
          <p role="alert" className="mb-5 border-l-2 border-ink py-1 pl-4 text-[14px]">
            {message}
          </p>
        )}
        <Decision fix={fix} approval={approval} />
        {fix.status === "waiting" && approval && <AutoRefresh />}
        {scanId && (
          <p className="mt-8 text-[14px]">
            <Link href={`/dashboard/scans/${scanId}`} className="underline decoration-rule underline-offset-4 hover:decoration-ink">
              Back to the scan
            </Link>
          </p>
        )}
      </Section>
    </>
  );
}

function Decision({ fix, approval }: { fix: Fix; approval: Approval | null }) {
  if (fix.status === "approved") {
    return (
      <Outcome title="Approved. The fix pull request is open.">
        {fix.pr_url ? (
          <a href={fix.pr_url} rel="noreferrer" target="_blank" className="underline underline-offset-4">
            {fix.pr_url.replace("https://github.com/", "")}
          </a>
        ) : (
          "The pull request link was not recorded."
        )}{" "}
        Merging it is still up to the pull request&apos;s author.
      </Outcome>
    );
  }
  if (fix.status === "rejected") {
    return <Outcome title="Rejected.">{approval?.reason || "No pull request was opened."}</Outcome>;
  }
  if (fix.status === "outdated") {
    return (
      <Outcome title="Approved, but not applied.">
        The pull request received new commits after this patch was made, so the approval no longer matched the code. Propose a new fix
        for the latest commit.
      </Outcome>
    );
  }
  if (fix.status !== "waiting") {
    return <Outcome title="Closed.">This fix is not waiting for a decision.</Outcome>;
  }
  if (approval) {
    return (
      <Outcome title={approval.decision === "approve" ? "You approved this patch." : "You rejected this patch."}>
        Recorded {formatDateTime(approval.decided_at)}. Sentinel&apos;s worker applies decisions within a few seconds while it is
        running. This page updates by itself.
      </Outcome>
    );
  }

  return (
    <div className="grid gap-8 border-t border-ink pt-6 md:grid-cols-2">
      <form action={decide} className="flex flex-col">
        <input type="hidden" name="fix_id" value={fix.id} />
        <input type="hidden" name="patch_id" value={fix.patch_id} />
        <input type="hidden" name="decision" value="approve" />
        <p className="text-[14px] text-muted">
          Opens a pull request with this exact diff into the branch of pull request #{fix.pr}. Nothing is merged. If the pull request
          changed since <span className="font-mono">{shortSha(fix.head_sha)}</span>, nothing is pushed.
        </p>
        <SubmitButton
          pending="Approving…"
          className="mt-5 inline-flex h-11 items-center justify-center self-start rounded-[4px] bg-ink px-5 font-medium text-paper transition-opacity hover:opacity-85"
        >
          Approve patch <span className="ml-2 font-mono text-[13px] opacity-80">{fix.patch_id}</span>
        </SubmitButton>
      </form>

      <form action={decide} className="flex flex-col">
        <input type="hidden" name="fix_id" value={fix.id} />
        <input type="hidden" name="patch_id" value={fix.patch_id} />
        <input type="hidden" name="decision" value="reject" />
        <label htmlFor="reason" className="text-[14px] text-muted">
          Reason <span className="text-muted/70">(optional, kept with the decision)</span>
        </label>
        <textarea
          id="reason"
          name="reason"
          maxLength={500}
          rows={3}
          className="mt-2 w-full resize-y rounded-[4px] border border-rule bg-surface px-3 py-2 text-[14px] focus:border-ink focus:outline-none"
        />
        <SubmitButton
          pending="Rejecting…"
          className="mt-3 inline-flex h-11 items-center justify-center self-start rounded-[4px] border border-ink/20 bg-surface px-5 font-medium transition-colors hover:border-ink/50"
        >
          Reject
        </SubmitButton>
      </form>
    </div>
  );
}

function Outcome({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-ink pt-5">
      <p className="font-medium">{title}</p>
      <p className="mt-1.5 max-w-[64ch] text-[14px] text-muted">{children}</p>
    </div>
  );
}

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-rule py-4 pr-4">
      <dt className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">{term}</dt>
      <dd className="mt-1.5 text-[14px]">{children}</dd>
    </div>
  );
}
