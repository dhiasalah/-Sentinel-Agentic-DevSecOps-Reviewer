import type { Metadata } from "next";

import { requireViewer } from "@/lib/auth";

export const metadata: Metadata = { title: "Overview · Sentinel" };

export default async function DashboardPage() {
  const viewer = await requireViewer();
  const firstName = viewer.name?.split(" ")[0];

  return (
    <div className="grid gap-8 lg:grid-cols-12">
      <p className="font-mono text-[12px] tracking-[0.08em] text-muted uppercase lg:col-span-3 lg:pt-2">Overview</p>
      <div className="lg:col-span-9">
        <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.01em]">
          {firstName ? `Welcome, ${firstName}.` : "Welcome."}
        </h1>

        <div className="mt-10 border-t border-ink">
          <div className="grid gap-x-8 gap-y-1 border-b border-rule py-5 sm:grid-cols-[12rem_1fr]">
            <span className="font-mono text-[12px] tracking-[0.08em] text-muted uppercase">Repositories</span>
            <span>None connected yet.</span>
          </div>
          <div className="grid gap-x-8 gap-y-1 border-b border-rule py-5 sm:grid-cols-[12rem_1fr]">
            <span className="font-mono text-[12px] tracking-[0.08em] text-muted uppercase">Scans</span>
            <span>No results stored yet. Reports still appear as comments on each pull request.</span>
          </div>
          <div className="grid gap-x-8 gap-y-1 border-b border-rule py-5 sm:grid-cols-[12rem_1fr]">
            <span className="font-mono text-[12px] tracking-[0.08em] text-muted uppercase">Waiting for you</span>
            <span>
              No fixes to review here yet. Use <code className="font-mono text-[13px]">sentinel review</code> in the
              terminal for now.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
