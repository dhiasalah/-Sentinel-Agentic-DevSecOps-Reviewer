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
