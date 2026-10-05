import "server-only";

import { createClient } from "@/lib/supabase/server";
import { DEFAULT_SETTINGS } from "@/lib/types";
import type { Approval, Fix, FixRequest, Issue, Repo, RepoSettings, Scan, ScanEvent, ScanStatus, Severity } from "@/lib/types";

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

export async function listFixRequests(issueIds: number[]): Promise<FixRequest[]> {
  if (issueIds.length === 0) return [];
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("fix_requests")
    .select("issue_id, status, fix_id, reason, requested_at, fix:fixes(status, pr_url)")
    .in("issue_id", issueIds)
    .overrideTypes<FixRequest[], { merge: false }>();
  if (error) fail("fix requests", error);
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

const EVENT_COLUMNS = "id, stage, status, scanner, count, at";

export async function listScanEvents(scanId: number): Promise<ScanEvent[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("scan_events")
    .select(EVENT_COLUMNS)
    .eq("scan_id", scanId)
    .order("id")
    .limit(200)
    .overrideTypes<ScanEvent[], { merge: false }>();
  if (error) fail("the scan's progress", error);
  return data;
}

// For the live stream: one client for the whole connection, asked again every poll.
// Status is read *before* events: the worker writes every event before it closes the scan,
// so once a poll sees a finished status, the events read right after it are complete.
export async function openScanFeed(scanId: number) {
  const supabase = await createClient();
  return {
    async status(): Promise<ScanStatus | null> {
      const { data, error } = await supabase.from("scans").select("status").eq("id", scanId).maybeSingle();
      if (error) fail("the scan", error);
      return (data?.status as ScanStatus | undefined) ?? null;
    },
    async eventsAfter(lastId: number): Promise<ScanEvent[]> {
      const { data, error } = await supabase
        .from("scan_events")
        .select(EVENT_COLUMNS)
        .eq("scan_id", scanId)
        .gt("id", lastId)
        .order("id")
        .limit(100)
        .overrideTypes<ScanEvent[], { merge: false }>();
      if (error) fail("the scan's progress", error);
      return data;
    },
  };
}

export async function getRepoSettings(repoId: number): Promise<RepoSettings> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("repo_settings")
    .select("scanners, report_min_severity, llm_order, updated_at")
    .eq("repo_id", repoId)
    .maybeSingle()
    .overrideTypes<RepoSettings | null, { merge: false }>();
  if (error) fail("the repository settings", error);
  return data ?? DEFAULT_SETTINGS;
}
