import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { saveSettings } from "@/app/dashboard/repos/[id]/settings/actions";
import { PageIntro, Section } from "@/components/page-intro";
import { SeverityMark } from "@/components/severity";
import { SubmitButton } from "@/components/submit-button";
import { getRepo, getRepoSettings, parseId } from "@/lib/data";
import { formatDateTime } from "@/lib/format";
import { LLM_ORDERS, SCANNERS, SEVERITIES, type ScannerName } from "@/lib/types";

export const metadata: Metadata = { title: "Settings · Sentinel" };

const SCANNER_INFO: Record<ScannerName, { looks: string; finds: string }> = {
  gitleaks: { looks: "Every file", finds: "Leaked secrets: API keys, tokens, passwords committed in the code." },
  semgrep: { looks: "Python files", finds: "Code flaws: injection, unsafe deserialization, debug mode, weak crypto." },
  trivy: { looks: "Lockfiles and requirements", finds: "Dependencies with known vulnerabilities (CVEs)." },
  checkov: { looks: "Dockerfiles, Terraform, YAML", finds: "Infrastructure misconfiguration: root containers, open ports, missing limits." },
};

const PROVIDER = { gemini: "Gemini", groq: "Groq" } as const;

const ERRORS: Record<string, string> = {
  "no-scanner": "Keep at least one scanner on. A scan with no scanner would report a clean pull request it never looked at.",
  invalid: "Those settings were not valid. Reload the page and try again.",
  denied: "Only the owner of this repository can change its settings.",
  failed: "The settings could not be saved. Try again.",
};

export default async function SettingsPage({ params, searchParams }: PageProps<"/dashboard/repos/[id]/settings">) {
  const id = parseId((await params).id);
  const repo = id ? await getRepo(id) : null;
  if (!repo) notFound();
  const settings = await getRepoSettings(repo.id);
  const { error, saved } = await searchParams;
  const message = typeof error === "string" ? ERRORS[error] : undefined;
  const order = settings.llm_order.join(",");

  return (
    <>
      <PageIntro
        label="Settings"
        crumbs={[
          { href: "/dashboard", label: "Overview" },
          { href: `/dashboard/repos/${repo.id}`, label: repo.full_name },
        ]}
      >
        <h1 className="font-serif text-[40px] leading-[1.05] tracking-[-0.02em]">How Sentinel reviews this repository</h1>
        <p className="mt-3 max-w-[64ch] text-muted">
          These choices live here, not in a file inside the repository, so a pull request cannot switch off the checks that review it.
          They apply from the next scan.
        </p>
        {message && (
          <p role="alert" className="mt-6 border-l-2 border-sev-critical py-1 pl-4 text-[14px]">
            {message}
          </p>
        )}
        {saved === "1" && !message && (
          <p role="status" className="mt-6 border-l-2 border-signal py-1 pl-4 text-[14px]">
            Saved. The next scan of {repo.full_name} uses these settings.
          </p>
        )}
      </PageIntro>

      <form action={saveSettings}>
        <input type="hidden" name="repo_id" value={repo.id} />

        <Section title="Scanners" aside="The planner still skips a scanner when the pull request has no file it reads.">
          <fieldset>
            <legend className="sr-only">Scanners to run</legend>
            <ul className="border-t border-ink">
              {SCANNERS.map((name) => (
                <li key={name} className="border-b border-rule">
                  <label className="grid cursor-pointer grid-cols-[auto_1fr] gap-x-4 py-4 sm:grid-cols-[auto_8rem_1fr]">
                    <input
                      type="checkbox"
                      name="scanners"
                      value={name}
                      defaultChecked={settings.scanners.includes(name)}
                      className="mt-1 size-4 accent-[var(--signal)]"
                    />
                    <span className="font-mono text-[14px]">{name}</span>
                    <span className="col-start-2 mt-1 text-[14px] sm:col-start-3 sm:mt-0">
                      {SCANNER_INFO[name].finds}
                      <span className="mt-0.5 block text-[13px] text-muted">Reads: {SCANNER_INFO[name].looks}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        </Section>

        <Section title="Comment threshold" aside="The dashboard always keeps every issue, and the score counts them all.">
          <fieldset>
            <legend className="text-[14px] text-muted">
              Lowest severity written in the pull request comment. Hidden issues are counted in the comment, never dropped silently.
            </legend>
            <div className="mt-4 flex flex-wrap border-t border-ink">
              {SEVERITIES.map((severity) => (
                <label
                  key={severity}
                  className="flex min-w-[8.5rem] flex-1 cursor-pointer items-center gap-3 border-b border-rule py-4 pr-4 has-[:checked]:border-ink"
                >
                  <input
                    type="radio"
                    name="report_min_severity"
                    value={severity}
                    defaultChecked={settings.report_min_severity === severity}
                    className="size-4 accent-[var(--signal)]"
                  />
                  <SeverityMark severity={severity} />
                  {severity !== "critical" && <span className="text-[13px] text-muted">and up</span>}
                </label>
              ))}
            </div>
          </fieldset>
        </Section>

        <Section title="AI provider" aside="The model groups findings, explains them and drafts fixes. It never decides alone.">
          <fieldset>
            <legend className="sr-only">Which provider is asked first</legend>
            <ul className="border-t border-ink">
              {LLM_ORDERS.map(([first, second]) => (
                <li key={first} className="border-b border-rule">
                  <label className="flex cursor-pointer items-start gap-4 py-4">
                    <input
                      type="radio"
                      name="llm_order"
                      value={`${first},${second}`}
                      defaultChecked={order === `${first},${second}`}
                      className="mt-1 size-4 accent-[var(--signal)]"
                    />
                    <span className="text-[14px]">
                      {PROVIDER[first]} first, {PROVIDER[second]} if it is down or answers badly
                    </span>
                  </label>
                </li>
              ))}
            </ul>
            <p className="mt-4 max-w-[64ch] border-l-2 border-sev-medium pl-4 text-[13px] text-muted">
              Both run on free tiers, and the code around each finding is sent to the provider. Free-tier prompts may be used to
              train models: only connect public or demo repositories.
            </p>
          </fieldset>
        </Section>

        <Section title="Save">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-ink pt-6">
            <SubmitButton
              pending="Saving…"
              className="inline-flex h-11 items-center justify-center rounded-[4px] bg-ink px-5 font-medium text-paper transition-opacity hover:opacity-85"
            >
              Save settings
            </SubmitButton>
            <span className="text-[13px] text-muted">
              {settings.updated_at ? `Last changed ${formatDateTime(settings.updated_at)}` : "Using the defaults: every scanner, every issue."}
            </span>
          </div>
        </Section>
      </form>
    </>
  );
}
