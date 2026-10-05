"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requireViewer } from "@/lib/auth";
import { parseId } from "@/lib/data";
import { createClient } from "@/lib/supabase/server";

// The browser sends one number: which issue. Row-level security accepts it only for your own issue from a finished
// scan that is not a leaked secret or a false positive; the worker reads the code and the commit from its own rows.
export async function requestFix(formData: FormData) {
  await requireViewer();
  const scanId = parseId(String(formData.get("scan_id") ?? ""));
  const issueId = parseId(String(formData.get("issue_id") ?? ""));
  if (!scanId) redirect("/dashboard");
  const back = `/dashboard/scans/${scanId}`;
  if (!issueId) redirect(`${back}?error=invalid#issue-${formData.get("issue_id")}`);

  const supabase = await createClient();
  const retry = formData.get("retry") === "1";
  const { data, error } = retry
    ? await supabase.from("fix_requests").update({ status: "queued" }).eq("issue_id", issueId).select("issue_id")
    : await supabase.from("fix_requests").insert({ issue_id: issueId }).select("issue_id");
  if (error || data.length === 0) {
    const reason = error?.code === "23505" ? "requested" : error?.code === "42501" || !error ? "denied" : "failed";
    redirect(`${back}?error=${reason}#issue-${issueId}`);
  }

  revalidatePath(back);
  redirect(`${back}#issue-${issueId}`);
}
