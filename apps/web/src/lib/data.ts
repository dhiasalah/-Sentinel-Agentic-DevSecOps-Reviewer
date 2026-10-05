import "server-only";

import { createClient } from "@/lib/supabase/server";
import type { Approval, Fix, Issue, Repo, Scan, Severity } from "@/lib/types";

// Every query runs as the signed-in user: row-level security decides what comes back.
// A row that isn't yours simply doesn't exist from here, so pages answer 404, not 403.

const SCAN_COLUMNS =
  "id, repo_id, pr, head_sha, status, finding_count, failed_scanners, started_at, finished_at, repo:repos(id, full_name), issues(severity)";

type ScanRow = Omit<Scan, "severities"> & { issues: { severity: Severity }[] };

function toScan({ issues, ...row }: ScanRow): Scan {
  return { ...row, severities: issues.map((i) => i.severity) };
}

function fail(what: string, error: { message: string }): never {
  throw new Error(`Could not load ${what}: ${error.message}`);
}

export async function listRepos(): Promise<Repo[]> {
  const supabase = await createClient();
  const { data, error } = await supabase.from("repos").select("id, full_name").order("full_name");
  if (error) fail("repositories", error);
  return data;
}

export async function getRepo(id: number): Promise<Repo | null> {
  const supabase = await createClient();
  const { data, error } = await supabase.from("repos").select("id, full_name").eq("id", id).maybeSingle();
  if (error) fail("the repository", error);
  return data;
}

export async function listScans({ repoId, limit = 50 }: { repoId?: number; limit?: number } = {}): Promise<Scan[]> {
  const supabase = await createClient();
  let query = supabase.from("scans").select(SCAN_COLUMNS).order("started_at", { ascending: false }).limit(limit);
  if (repoId !== undefined) query = query.eq("repo_id", repoId);
  const { data, error } = await query.overrideTypes<ScanRow[], { merge: false }>();
  if (error) fail("scans", error);
  return data.map(toScan);
}

export async function getScan(id: number): Promise<Scan | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("scans")
    .select(SCAN_COLUMNS)
    .eq("id", id)
    .maybeSingle()
    .overrideTypes<ScanRow | null, { merge: false }>();
  if (error) fail("the scan", error);
  return data ? toScan(data) : null;
}

export async function listIssues(scanId: number): Promise<Issue[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("issues")
    .select("id, severity, title, explanation, fix, false_positive, review_reasons, findings")
    .eq("scan_id", scanId)
    .order("id")
    .overrideTypes<Issue[], { merge: false }>();
  if (error) fail("issues", error);
  return data;
}

const FIX_COLUMNS =
  "id, repo_id, pr, head_sha, issue_title, summary, provider, diff, patch_id, scanners, status, pr_url, created_at, repo:repos(id, full_name)";

export async function listFixes({ status, limit = 20 }: { status?: Fix["status"]; limit?: number } = {}): Promise<Fix[]> {
  const supabase = await createClient();
  let query = supabase.from("fixes").select(FIX_COLUMNS).order("created_at", { ascending: false }).limit(limit);
  if (status) query = query.eq("status", status);
  const { data, error } = await query.overrideTypes<Fix[], { merge: false }>();
  if (error) fail("fixes", error);
  return data;
}

export async function getFix(id: string): Promise<Fix | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("fixes")
    .select(FIX_COLUMNS)
    .eq("id", id)
    .maybeSingle()
    .overrideTypes<Fix | null, { merge: false }>();
  if (error) fail("the fix", error);
  return data;
}

export async function getApproval(fixId: string): Promise<Approval | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("approvals")
    .select("decision, patch_id, reason, decided_at")
    .eq("fix_id", fixId)
    .maybeSingle()
    .overrideTypes<Approval | null, { merge: false }>();
  if (error) fail("the decision", error);
  return data;
}

export function isFixId(raw: string): boolean {
  return /^fix-[0-9a-f]{8}$/.test(raw);
}

// Route params come from the URL: only plain positive integers reach the database.
export function parseId(raw: string): number | null {
  return /^[1-9][0-9]{0,15}$/.test(raw) ? Number(raw) : null;
}
