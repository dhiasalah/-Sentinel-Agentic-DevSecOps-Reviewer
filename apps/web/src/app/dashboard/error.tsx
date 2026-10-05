"use client";

import Link from "next/link";
import { useEffect } from "react";

import { PageIntro } from "@/components/page-intro";

// A dashboard page that failed to load (Supabase down, a missing migration...). The error text is not shown:
// it can contain database details. The digest matches the server log line.
export default function DashboardError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <PageIntro label="Error">
      <h1 className="font-serif text-[40px] leading-[1.05] tracking-[-0.02em]">This page could not load.</h1>
      <p className="mt-4 max-w-[52ch] text-muted">
        Sentinel could not read its data just now. Nothing was changed. Try again, and if it keeps failing, check the
        server logs.
        {error.digest && (
          <span className="mt-2 block font-mono text-[12px]">Reference {error.digest}</span>
        )}
      </p>
      <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
        <button
          type="button"
          onClick={() => retry()}
          className="inline-flex h-11 items-center rounded-[4px] bg-ink px-5 font-medium text-paper transition-opacity hover:opacity-85"
        >
          Try again
        </button>
        <Link href="/dashboard" className="underline decoration-rule underline-offset-[6px] hover:decoration-ink">
          Back to the overview
        </Link>
      </div>
    </PageIntro>
  );
}
