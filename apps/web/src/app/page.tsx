import Link from "next/link";

import { PatchSpecimen } from "@/components/patch-specimen";
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
      <header className="flex items-center justify-between py-6">
        <Wordmark />
        <nav className="flex items-center gap-7 text-[14px]">
          <a href={REPO_URL} className="hidden text-muted transition-colors hover:text-ink sm:inline">
            Source
          </a>
          <Link
            href="/login"
            className="rounded-[4px] border border-ink/15 bg-surface px-3.5 py-1.5 font-medium transition-colors hover:border-ink/40"
          >
            Sign in
          </Link>
        </nav>
      </header>

      <main className="flex-1">
        <section className="grid items-center gap-14 pt-14 pb-20 sm:pt-20 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:pb-28">
          <div>
            <p className="font-mono text-[12px] tracking-[0.08em] text-muted uppercase">Pull request security review</p>
            <h1 className="mt-5 font-serif text-[clamp(2.4rem,5.2vw,4rem)] leading-[1.02] font-normal tracking-[-0.02em] text-balance">
              Every fix is <em className="text-signal">proposed</em> by a model and <em>decided</em> by a person.
            </h1>
            <p className="mt-7 max-w-[52ch] text-[17px] leading-[1.65] text-pretty text-muted">
              Sentinel reviews the pull requests of the repositories it is installed on. It explains what the scanners
              found, drafts a minimal patch, tests it in isolation, and opens a fix pull request only after someone
              approves the exact diff.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-x-6 gap-y-3">
              <Link
                href="/login"
                className="inline-flex h-11 items-center rounded-[4px] bg-ink px-5 font-medium text-paper transition-opacity hover:opacity-85"
              >
                Open the dashboard
              </Link>
              <a href="#how" className="text-[15px] underline decoration-rule underline-offset-[6px] hover:decoration-ink">
                How a finding becomes a fix
              </a>
            </div>
          </div>

          <PatchSpecimen />
        </section>

        <section id="how" className="scroll-mt-8 border-t border-ink pb-24">
          <div className="grid gap-x-8 gap-y-3 pt-8 pb-6 lg:grid-cols-12">
            <h2 className="font-serif text-[30px] leading-tight tracking-[-0.01em] text-balance lg:col-span-5">
              From finding to fix, in six checked steps
            </h2>
            <p className="max-w-[52ch] text-muted lg:col-span-6 lg:col-start-7 lg:pt-2">
              Each step can stop the run. Nothing reaches your repository without passing all of them, and the last
              word is always yours.
            </p>
          </div>

          <ol>
            {stages.map((stage, i) => (
              <li key={stage.name} className="grid gap-x-8 gap-y-2 border-t border-rule py-7 lg:grid-cols-12">
                <div className="flex items-baseline gap-4 lg:col-span-3">
                  <span className="font-mono text-[12px] text-muted tabular-nums">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="font-serif text-[21px] leading-none">{stage.name}</h3>
                </div>
                <p className="lg:col-span-5">{stage.does}</p>
                <p className="border-l-2 border-signal pl-4 text-[14px] text-muted lg:col-span-4">{stage.guard}</p>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer className="flex flex-col gap-2 border-t border-rule py-7 text-[13px] text-muted sm:flex-row sm:justify-between">
        <span>A learning project in agents, DevOps and security.</span>
        <a href={REPO_URL} className="transition-colors hover:text-ink">
          Source on GitHub
        </a>
      </footer>
    </div>
  );
}
