import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PageIntro, Section } from "@/components/page-intro";
import { ScanProgress } from "@/components/scan-progress";
import { ScanStatusBadge } from "@/components/scan-status";
import { SeverityCounts, SeverityMark } from "@/components/severity";
import { getScan, listIssues, listScanEvents, parseId } from "@/lib/data";
import { formatDateTime, formatDuration, plural, shortSha } from "@/lib/format";
import type { Issue } from "@/lib/types";

export const metadata: Metadata = { title: "Scan · Sentinel" };

export default async function ScanPage({ params }: PageProps<"/dashboard/scans/[id]">) {
  const id = parseId((await params).id);
  const scan = id ? await getScan(id) : null;
  if (!scan) notFound();
  const [issues, events] = await Promise.all([scan.status === "done" ? listIssues(scan.id) : [], listScanEvents(scan.id)]);
  const live = scan.status === "running";
  const github = `https://github.com/${scan.repo.full_name}`;
  const duration = formatDuration(scan.started_at, scan.finished_at);

  return (
    <>
      <PageIntro
        label={`Scan ${scan.id}`}
        crumbs={[
          { href: "/dashboard", label: "Overview" },
          { href: `/dashboard/repos/${scan.repo.id}`, label: scan.repo.full_name },
        ]}
      >
        <h1 className="font-serif text-[40px] leading-[1.05] tracking-[-0.02em]">
          Pull request #{scan.pr}
          <span className="ml-3 align-middle font-mono text-[15px] tracking-normal text-muted">{shortSha(scan.head_sha)}</span>
        </h1>

        <dl className="mt-8 grid grid-cols-2 border-t border-ink sm:grid-cols-4">
          <Fact term="Status">
            <ScanStatusBadge status={scan.status} incomplete={scan.failed_scanners.length > 0} />
          </Fact>
          <Fact term="Started">{formatDateTime(scan.started_at)}</Fact>
          <Fact term="Duration">{duration ?? "—"}</Fact>
          <Fact term="Findings">
            {scan.status === "done" ? `${scan.finding_count} → ${plural(issues.length, "issue")}` : "—"}
          </Fact>
        </dl>

        <p className="mt-5 flex flex-wrap gap-x-5 gap-y-1 text-[14px]">
          <a href={`${github}/pull/${scan.pr}`} rel="noreferrer" target="_blank" className="underline decoration-rule underline-offset-4 hover:decoration-ink">
            Pull request on GitHub
          </a>
          <a href={`${github}/commit/${scan.head_sha}`} rel="noreferrer" target="_blank" className="underline decoration-rule underline-offset-4 hover:decoration-ink">
            Scanned commit
          </a>
        </p>

        {scan.failed_scanners.length > 0 && (
          <Notice title="This scan is incomplete.">
            {scan.failed_scanners.join(", ")} failed, so issues may be missing. Re-run the scan before relying on this report.
          </Notice>
        )}
        {scan.status === "failed" && (
          <Notice title="This scan did not finish.">
            Nothing was reported for this commit, and the pull request did not get a comment from this run.
          </Notice>
        )}
      </PageIntro>

      {(live || events.length > 0) && (
        <Section title={live ? "In progress" : "Run log"} aside={live ? "Updates as the agents work" : "Each step of this scan"}>
          {/* The key remounts the log when the status changes, so the finished page starts from the stored events. */}
          <ScanProgress key={scan.status} scanId={scan.id} startedAt={scan.started_at} initialEvents={events} live={live} />
        </Section>
      )}

      {scan.status === "done" && (
        <Section title="Issues" aside={<SeverityCounts severities={scan.severities} />}>
          {issues.length === 0 ? (
            <p className="border-t border-rule py-5 text-muted">The scanners that ran found nothing.</p>
          ) : (
            <ol className="border-t border-ink">
              {issues.map((issue) => (
                <IssueItem key={issue.id} issue={issue} />
              ))}
            </ol>
          )}
        </Section>
      )}
    </>
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

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div role="status" className="mt-6 border-l-2 border-sev-medium bg-surface py-3 pr-4 pl-4 text-[14px]">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-muted">{children}</p>
    </div>
  );
}

// Titles, explanations and fixes are written by a model that read the pull request's code.
// They are rendered as plain text (React escapes them) and labelled as AI-written.
function IssueItem({ issue }: { issue: Issue }) {
  const locations = [...new Map(issue.findings.map((f) => [`${f.file}:${f.line}`, f])).values()];
  return (
    <li className="border-b border-rule py-7">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <SeverityMark severity={issue.severity} />
        {issue.false_positive && (
          <span className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">AI thinks: false positive</span>
        )}
      </div>
      <h3 className="mt-2 font-serif text-[22px] leading-snug">{issue.title}</h3>

      {issue.review_reasons.map((reason) => (
        <p key={reason} className="mt-3 border-l-2 border-sev-medium pl-3 text-[14px]">
          Needs human review: {reason}
        </p>
      ))}

      <div className="mt-4 grid gap-4 md:grid-cols-2 md:gap-8">
        <div>
          <p className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">Why it matters</p>
          <p className="mt-1.5 text-[14px] leading-relaxed">{issue.explanation}</p>
        </div>
        <div>
          <p className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">Suggested fix</p>
          <p className="mt-1.5 text-[14px] leading-relaxed">{issue.fix}</p>
        </div>
      </div>

      <details className="mt-4 text-[13px]">
        <summary className="cursor-pointer text-muted hover:text-ink">
          {plural(locations.length, "location")} · {plural(issue.findings.length, "scanner finding")}
        </summary>
        <ul className="mt-2 space-y-1 font-mono text-[12px]">
          {issue.findings.map((f, i) => (
            <li key={i} className="flex flex-wrap gap-x-3">
              <span>
                {f.file}:{f.line}
              </span>
              <span className="text-muted">
                {f.tool} · {f.rule_id}
              </span>
            </li>
          ))}
        </ul>
      </details>
    </li>
  );
}
