import type { Metadata } from "next";
import Link from "next/link";

import { PageIntro, Section } from "@/components/page-intro";
import { ScanStatusBadge } from "@/components/scan-status";
import { ScanTable } from "@/components/scan-table";
import { requireViewer } from "@/lib/auth";
import { listFixes, listRepos, listScans } from "@/lib/data";
import { formatRelative, plural, shortSha } from "@/lib/format";

export const metadata: Metadata = { title: "Overview · Sentinel" };

export default async function DashboardPage() {
  const viewer = await requireViewer();
  const [repos, scans, fixes] = await Promise.all([listRepos(), listScans({ limit: 8 }), listFixes({ status: "waiting" })]);
  const waiting = fixes.length;
  const firstName = viewer.name?.split(" ")[0];
  const latest = new Map<number, (typeof scans)[number]>();
  for (const scan of scans) if (!latest.has(scan.repo_id)) latest.set(scan.repo_id, scan);
  const now = new Date();

  return (
    <>
      <PageIntro label="Overview">
        <h1 className="font-serif text-[40px] leading-[1.05] tracking-[-0.02em]">
          {firstName ? `Welcome, ${firstName}.` : "Welcome."}
        </h1>
        <p className="mt-3 text-muted">
          {plural(repos.length, "repository")} · {waiting === 0 ? "no fixes waiting for you" : `${plural(waiting, "fix")} waiting for you`}
        </p>
      </PageIntro>

      <Section title="Repositories">
        {repos.length === 0 ? (
          <p className="border-t border-rule py-5 text-muted">
            No repository is linked to your account yet. Scans are only stored for linked repositories.
          </p>
        ) : (
          <ul className="border-t border-ink">
            {repos.map((repo) => {
              const scan = latest.get(repo.id);
              return (
                <li key={repo.id} className="border-b border-rule">
                  <Link
                    href={`/dashboard/repos/${repo.id}`}
                    className="group flex flex-col gap-1 py-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <span className="font-mono text-[14px] underline-offset-4 [overflow-wrap:anywhere] group-hover:underline">{repo.full_name}</span>
                    <span className="flex items-center gap-3 text-[13px] text-muted">
                      {scan ? (
                        <>
                          <ScanStatusBadge status={scan.status} incomplete={scan.failed_scanners.length > 0} />
                          <span>
                            PR #{scan.pr} · <span className="font-mono">{shortSha(scan.head_sha)}</span> ·{" "}
                            {formatRelative(scan.started_at, now)}
                          </span>
                        </>
                      ) : (
                        "No scans yet"
                      )}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section title="Recent scans" aside="Across all your repositories">
        <ScanTable scans={scans} />
      </Section>

      <Section title="Waiting for you" aside="Fixes that passed the sandbox">
        {fixes.length === 0 ? (
          <p className="border-t border-rule py-5 text-muted">
            Nothing to review. Proposed fixes will appear here once they pass the sandbox.
          </p>
        ) : (
          <ul className="border-t border-ink">
            {fixes.map((fix) => (
              <li key={fix.id} className="border-b border-rule">
                <Link
                  href={`/dashboard/fixes/${fix.id}`}
                  className="group flex flex-col gap-1 py-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="underline-offset-4 [overflow-wrap:anywhere] group-hover:underline">{fix.issue_title}</span>
                  <span className="text-[13px] text-muted">
                    <span className="font-mono">{fix.repo.full_name}</span> · PR #{fix.pr} · {formatRelative(fix.created_at, now)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}
