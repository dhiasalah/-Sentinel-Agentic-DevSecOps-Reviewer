import Link from "next/link";

import { PageIntro } from "@/components/page-intro";

// Shown for ids that don't exist and for rows row-level security hides: the two look the same on purpose.
export default function DashboardNotFound() {
  return (
    <PageIntro label="Not found">
      <h1 className="font-serif text-[40px] leading-[1.05] tracking-[-0.02em]">Nothing here.</h1>
      <p className="mt-4 max-w-[52ch] text-muted">
        This page doesn&apos;t exist, or it belongs to a repository that isn&apos;t linked to your account.
      </p>
      <Link href="/dashboard" className="mt-8 inline-block underline decoration-rule underline-offset-[6px] hover:decoration-ink">
        Back to the overview
      </Link>
    </PageIntro>
  );
}
