import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PageIntro, Section } from "@/components/page-intro";
import { ScanTable } from "@/components/scan-table";
import { getRepo, listScans, parseId } from "@/lib/data";
import { plural } from "@/lib/format";

export const metadata: Metadata = { title: "Repository · Sentinel" };

export default async function RepoPage({ params }: PageProps<"/dashboard/repos/[id]">) {
  const id = parseId((await params).id);
  const repo = id ? await getRepo(id) : null;
  if (!repo) notFound();
  const scans = await listScans({ repoId: repo.id });
  const done = scans.filter((s) => s.status === "done").length;
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
        </p>
      </PageIntro>

      <Section title="Scan history" aside="Newest first">
        <ScanTable scans={scans} showRepo={false} />
      </Section>
    </>
  );
}
