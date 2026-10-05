import Link from "next/link";

import { ScanStatusBadge } from "@/components/scan-status";
import { SeverityCounts } from "@/components/severity";
import { formatDateTime, formatRelative, shortSha } from "@/lib/format";
import type { Scan } from "@/lib/types";

export function ScanTable({ scans, showRepo = true }: { scans: Scan[]; showRepo?: boolean }) {
  if (scans.length === 0) {
    return <p className="border-t border-rule py-5 text-muted">No scans stored yet. They appear after the next pull request event.</p>;
  }
  const now = new Date();

  return (
    <table className="w-full border-collapse text-left">
      <thead>
        <tr className="border-t border-ink font-mono text-[11px] tracking-[0.06em] text-muted uppercase">
          <th scope="col" className="py-3 pr-6 font-normal">Pull request</th>
          {showRepo && <th scope="col" className="hidden py-3 pr-6 font-normal md:table-cell">Repository</th>}
          <th scope="col" className="py-3 pr-6 font-normal">Status</th>
          <th scope="col" className="hidden py-3 pr-6 font-normal sm:table-cell">Issues</th>
          <th scope="col" className="py-3 text-right font-normal">Started</th>
        </tr>
      </thead>
      <tbody>
        {scans.map((scan) => (
          <tr key={scan.id} className="group border-t border-rule">
            <td className="py-4 pr-6">
              <Link href={`/dashboard/scans/${scan.id}`} className="underline-offset-4 group-hover:underline">
                PR #{scan.pr}
              </Link>
              <span className="ml-2 font-mono text-[12px] text-muted">{shortSha(scan.head_sha)}</span>
            </td>
            {showRepo && (
              <td className="hidden py-4 pr-6 font-mono text-[13px] md:table-cell">{scan.repo.full_name}</td>
            )}
            <td className="py-4 pr-6">
              <ScanStatusBadge status={scan.status} incomplete={scan.failed_scanners.length > 0} />
            </td>
            <td className="hidden py-4 pr-6 sm:table-cell">
              {scan.status === "done" ? <SeverityCounts severities={scan.severities} /> : <span className="text-muted">—</span>}
            </td>
            <td className="py-4 text-right text-[13px] text-muted" title={formatDateTime(scan.started_at)}>
              {formatRelative(scan.started_at, now)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
