import Link from "next/link";

import { signOut } from "@/app/auth/actions";
import { SubmitButton } from "@/components/submit-button";
import { Wordmark } from "@/components/wordmark";
import { requireViewer } from "@/lib/auth";

export default async function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  const viewer = await requireViewer();

  return (
    <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-5 sm:px-8">
      <header className="flex items-center justify-between gap-6 border-b border-rule py-5">
        <div className="flex items-center gap-8">
          <Link href="/dashboard" aria-label="Dashboard">
            <Wordmark />
          </Link>
          <nav className="hidden font-mono text-[13px] sm:block">
            <Link href="/dashboard" className="text-ink">
              Overview
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-5 font-mono text-[13px]">
          <span className="text-muted" title={viewer.name ?? undefined}>
            @{viewer.login}
          </span>
          <form action={signOut}>
            <SubmitButton pending="Signing out…" className="text-muted underline-offset-4 transition-colors hover:text-ink hover:underline">
              Sign out
            </SubmitButton>
          </form>
        </div>
      </header>
      <main className="flex-1 py-12">{children}</main>
    </div>
  );
}
