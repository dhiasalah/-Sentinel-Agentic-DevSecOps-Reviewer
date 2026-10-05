import Link from "next/link";

import { Wordmark } from "@/components/wordmark";

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-5 sm:px-8">
      <header className="py-6">
        <Link href="/" aria-label="Sentinel home">
          <Wordmark />
        </Link>
      </header>
      <main className="grid flex-1 content-start gap-8 py-16 sm:py-24 lg:grid-cols-12">
        <p className="font-mono text-[12px] tracking-[0.08em] text-muted uppercase lg:col-span-3 lg:pt-3">404</p>
        <div className="lg:col-span-9">
          <h1 className="font-serif text-[40px] leading-[1.05] tracking-[-0.02em]">This page doesn&apos;t exist.</h1>
          <Link href="/" className="mt-8 inline-block underline decoration-rule underline-offset-[6px] hover:decoration-ink">
            Back to the home page
          </Link>
        </div>
      </main>
    </div>
  );
}
