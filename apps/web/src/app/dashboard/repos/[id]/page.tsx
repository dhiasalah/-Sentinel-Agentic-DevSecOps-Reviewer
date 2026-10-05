import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PageIntro, Section } from "@/components/page-intro";
import { ScanTable } from "@/components/scan-table";
import { ScoreTrend } from "@/components/score-trend";
import { getRepo, listScans, parseId } from "@/lib/data";
import { plural } from "@/lib/format";
import { PENALTY, scoreHistory, type ScorePoint } from "@/lib/score";

export const metadata: Metadata = { title: "Repository · Sentinel" };

export default async function RepoPage({ params }: PageProps<"/dashboard/repos/[id]">) {
  const id = parseId((await params).id);
  const repo = id ? await getRepo(id) : null;
  if (!repo) notFound();
  const scans = await listScans({ repoId: repo.id });
  const done = scans.filter((s) => s.status === "done").length;
  const history = scoreHistory(scans);
  const [owner, name] = repo.full_name.split("/");

  return (
    <>
      <PageIntro label="Repository" crumbs={[{ href: "/dashboard", label: "Overview" }]}>
        <h1 className="font-mono text-[21px] leading-tight tracking-[-0.01em] sm:text-[26px]">
          {owner}/<wbr />
          {name}
        </h1>
        <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-muted">
          <span>
            {plural(scans.length, "scan")}, {done} completed
          </span>
          <a
            href={`https://github.com/${repo.full_name}`}
            rel="noreferrer"
            target="_blank"
            className="underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-ink"
          >
            Open on GitHub
          </a>
          <Link href={`/dashboard/repos/${repo.id}/settings`} className="underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-ink">
            Settings
          </Link>
        </p>
      </PageIntro>

      <Section
        title="Security score"
        aside={`100 minus ${PENALTY.critical} per critical, ${PENALTY.high} per high, ${PENALTY.medium} per medium, ${PENALTY.low} per low issue.`}
      >
        {history.length === 0 ? (
          <p className="border-t border-rule py-5 text-muted">A score appears after the first completed scan.</p>
        ) : (
          <>
            <Headline history={history} />
            <div className="mt-8">
              <ScoreTrend points={history} />
            </div>
          </>
        )}
      </Section>

      <Section title="Scan history" aside="Newest first">
        <ScanTable scans={scans} showRepo={false} />
      </Section>
    </>
  );
}

// The latest score and how it moved since the scan before it. Up is good.
function Headline({ history }: { history: ScorePoint[] }) {
  const latest = history[history.length - 1];
  const previous = history.length > 1 ? history[history.length - 2] : null;
  const delta = previous ? latest.score - previous.score : 0;
  return (
    <div className="flex flex-wrap items-end gap-x-6 gap-y-2 border-t border-ink pt-5">
      <p className="text-[56px] leading-none font-semibold tracking-[-0.02em]">
        {latest.score}
        <span className="ml-1 text-[18px] font-normal text-muted">/ 100</span>
      </p>
      <p className="pb-1.5 text-[14px] text-muted">
        {previous === null ? (
          "First completed scan"
        ) : delta === 0 ? (
          "Unchanged since the previous scan"
        ) : (
          <>
            <span className={delta > 0 ? "text-signal" : "text-sev-critical"}>
              {delta > 0 ? "▲" : "▼"} {Math.abs(delta)}
            </span>{" "}
            since PR #{previous.pr}
          </>
        )}
        {latest.incomplete && " · latest scan incomplete, the score may be too kind"}
      </p>
    </div>
  );
}
