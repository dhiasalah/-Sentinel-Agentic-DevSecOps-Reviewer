import Link from "next/link";

import { Wordmark } from "@/components/wordmark";

const REPO_URL = "https://github.com/dhiasalah/-Sentinel-Agentic-DevSecOps-Reviewer";

const stages = [
  {
    name: "Scan",
    does: "Semgrep, Gitleaks, Trivy and Checkov run in containers behind an MCP server, chosen by the files in the pull request.",
    guard: "Scanner output is validated. If a scanner fails, the report says it is incomplete instead of looking clean.",
  },
  {
    name: "Triage",
    does: "Findings are grouped into issues and explained in plain language by Gemini, with Groq as a fallback.",
    guard: "Repository text is passed as untrusted data. If the model lowers a severity below the scanner's, the issue is flagged for review.",
  },
  {
    name: "Fix",
    does: "For one issue, the fixer asks for search-and-replace edits close to the reported lines and turns them into a diff.",
    guard: "No automatic fix for leaked secrets, or for files that try to address the model.",
  },
  {
    name: "Sandbox",
    does: "The patch is applied to a copy of the repository in a container with no network and a read-only filesystem, then scanned again.",
    guard: "Patches that delete or rename files, break syntax or add findings are rejected.",
  },
  {
    name: "Approval",
    does: "A person reads the diff and approves it by its fingerprint.",
    guard: "If the pull request changed after the patch was made, the approval is not used and nothing is pushed.",
  },
  {
    name: "Fix PR",
    does: (
      <>
        The patch is committed to a new <code className="font-mono text-[13px]">sentinel/</code> branch and opened
        as a pull request into the author&apos;s branch.
      </>
    ),
    guard: "The default branch is protected. Merging stays a human decision.",
  },
];

export default function Home() {
  return (
    <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-5 sm:px-8">
      <header className="flex items-center justify-between border-b border-rule py-5">
        <Wordmark />
        <nav className="flex items-center gap-6 font-mono text-[13px]">
          <a href={REPO_URL} className="hidden text-muted transition-colors hover:text-ink sm:inline">
            Source on GitHub
          </a>
          <Link href="/login" className="text-ink underline-offset-4 hover:underline">
            Sign in
          </Link>
        </nav>
      </header>

      <main className="flex-1">
        <section className="grid gap-8 py-16 sm:py-24 lg:grid-cols-12">
          <p className="font-mono text-[12px] tracking-[0.08em] text-muted uppercase lg:col-span-3 lg:pt-3">
            Pull request security review
          </p>
          <div className="lg:col-span-9">
            <h1 className="max-w-[22ch] text-[clamp(2rem,4.6vw,3.4rem)] leading-[1.08] font-semibold tracking-[-0.02em] text-balance">
              Scanners find the problem. A model explains it and drafts a fix. A person decides.
            </h1>
            <p className="mt-6 max-w-[62ch] text-[17px] text-pretty text-muted">
              Sentinel reviews every pull request on the repositories it is installed on. It posts one report per
              pull request, proposes a minimal patch for an issue, tests that patch in isolation, and opens a fix
              pull request only after someone approves the exact diff.
            </p>
          </div>
        </section>

        <section className="border-t border-ink pb-20">
          <div className="grid gap-x-8 gap-y-2 py-5 lg:grid-cols-12">
            <h2 className="font-mono text-[12px] tracking-[0.08em] uppercase lg:col-span-3">
              From finding to fix
            </h2>
            <p className="text-muted lg:col-span-9">Six stages. Each one has a check that can stop the run.</p>
          </div>

          <ol>
            {stages.map((stage, i) => (
              <li key={stage.name} className="grid gap-x-8 gap-y-2 border-t border-rule py-6 lg:grid-cols-12">
                <div className="flex items-baseline gap-4 lg:col-span-3">
                  <span className="font-mono text-[12px] text-muted tabular-nums">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="font-medium">{stage.name}</h3>
                </div>
                <p className="lg:col-span-5">{stage.does}</p>
                <p className="border-l-2 border-signal pl-4 text-[14px] text-muted lg:col-span-4">{stage.guard}</p>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer className="flex flex-col gap-2 border-t border-rule py-6 font-mono text-[12px] text-muted sm:flex-row sm:justify-between">
        <span>A learning project in agents, DevOps and security.</span>
        <a href={REPO_URL} className="transition-colors hover:text-ink">
          Source on GitHub
        </a>
      </footer>
    </div>
  );
}
