import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signInWithGitHub } from "@/app/auth/actions";
import { GitHubMark } from "@/components/github-mark";
import { SubmitButton } from "@/components/submit-button";
import { Wordmark } from "@/components/wordmark";
import { getViewer } from "@/lib/auth";

export const metadata: Metadata = { title: "Sign in · Sentinel" };

const ERRORS: Record<string, string> = {
  callback: "GitHub sign-in did not complete. Try again.",
  provider: "Sign-in could not start. Try again in a moment.",
  origin: "The request was rejected. Reload the page and try again.",
};

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  if (await getViewer()) redirect("/dashboard");
  const { error } = await searchParams;
  const message = typeof error === "string" ? ERRORS[error] : undefined;

  return (
    <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-5 sm:px-8">
      <header className="flex items-center justify-between py-6">
        <Link href="/" aria-label="Sentinel home">
          <Wordmark />
        </Link>
      </header>

      <main className="grid flex-1 content-start gap-8 py-16 sm:py-24 lg:grid-cols-12">
        <p className="font-mono text-[12px] tracking-[0.08em] text-muted uppercase lg:col-span-3 lg:pt-2">Sign in</p>

        <div className="max-w-md lg:col-span-6">
          <h1 className="font-serif text-[40px] leading-[1.05] tracking-[-0.02em]">Sign in to the dashboard</h1>
          <p className="mt-4 text-[16px] text-muted">
            Use your GitHub account. Sentinel reads your public profile and email address, nothing else.
          </p>

          {message && (
            <p role="alert" className="mt-6 border-l-2 border-ink py-1 pl-4 text-[14px]">
              {message}
            </p>
          )}

          <form action={signInWithGitHub} className="mt-8">
            <SubmitButton
              pending={
                <>
                  <GitHubMark className="size-[18px]" />
                  Opening GitHub…
                </>
              }
              className="inline-flex h-11 items-center gap-3 rounded-[4px] bg-ink px-5 font-medium text-paper transition-opacity hover:opacity-85"
            >
              <GitHubMark className="size-[18px]" />
              Continue with GitHub
            </SubmitButton>
          </form>

          <p className="mt-10 border-t border-rule pt-5 text-[14px] text-muted">
            Access to repositories is separate: it comes from the Sentinel GitHub App installed on each repository,
            not from your sign-in.
          </p>
        </div>
      </main>
    </div>
  );
}
