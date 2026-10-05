export type Severity = "critical" | "high" | "medium" | "low" | "info";

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

export type ScanStatus = "running" | "done" | "failed";

export type Repo = {
  id: number;
  full_name: string;
};

export type Scan = {
  id: number;
  repo_id: number;
  pr: number;
  head_sha: string;
  status: ScanStatus;
  finding_count: number;
  failed_scanners: string[];
  started_at: string;
  finished_at: string | null;
  repo: Repo;
  severities: Severity[];
};

export type Finding = {
  tool: string;
  rule_id: string;
  severity: string;
  message: string;
  file: string;
  line: number;
  end_line?: number | null;
  cwe?: string[];
};

export type Issue = {
  id: number;
  severity: Severity;
  title: string;
  explanation: string;
  fix: string;
  false_positive: boolean;
  review_reasons: string[];
  findings: Finding[];
};

export type FixStatus = "waiting" | "approved" | "rejected" | "outdated" | "refused" | "not_verified" | "no_fix";

export type Fix = {
  id: string;
  repo_id: number;
  pr: number;
  head_sha: string;
  issue_title: string;
  summary: string;
  provider: string;
  diff: string;
  patch_id: string;
  scanners: string[];
  status: FixStatus;
  pr_url: string | null;
  created_at: string;
  repo: Repo;
};

export type Approval = {
  decision: "approve" | "reject";
  patch_id: string;
  reason: string;
  decided_at: string;
};

export type FixRequestStatus = "queued" | "working" | "waiting" | "refused" | "no_fix" | "not_verified" | "failed";

// A fix asked for from the scan page. The worker fills status and fix_id; the browser only ever sends issue_id.
export type FixRequest = {
  issue_id: number;
  status: FixRequestStatus;
  fix_id: string | null;
  requested_at: string;
  fix: { status: FixStatus; pr_url: string | null } | null;
};

export type ScanEventStage = "checkout" | "plan" | "scanner" | "triage" | "report";
export type ScanEventStatus = "started" | "ok" | "failed" | "skipped";

// One step of a scan, written by the worker. Only fixed words and numbers: nothing a model or a PR wrote.
export type ScanEvent = {
  id: number;
  stage: ScanEventStage;
  status: ScanEventStatus;
  scanner: string | null;
  count: number | null;
  at: string;
};

export const SCANNERS = ["gitleaks", "semgrep", "trivy", "checkov"] as const;
export type ScannerName = (typeof SCANNERS)[number];

export const LLM_ORDERS = [
  ["gemini", "groq"],
  ["groq", "gemini"],
] as const;
export type LlmOrder = (typeof LLM_ORDERS)[number];

export type RepoSettings = {
  scanners: ScannerName[];
  report_min_severity: Severity;
  llm_order: LlmOrder;
  updated_at: string | null;
};

// Same defaults as the database and the worker: when in doubt, scan everything and report everything.
export const DEFAULT_SETTINGS: RepoSettings = {
  scanners: [...SCANNERS],
  report_min_severity: "info",
  llm_order: LLM_ORDERS[0],
  updated_at: null,
};
