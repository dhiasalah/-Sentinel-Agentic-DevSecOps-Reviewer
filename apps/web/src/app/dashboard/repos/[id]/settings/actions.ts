"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requireViewer } from "@/lib/auth";
import { parseId } from "@/lib/data";
import { createClient } from "@/lib/supabase/server";
import { LLM_ORDERS, SCANNERS, SEVERITIES } from "@/lib/types";

// Only known values survive: the form is a suggestion, the lists below (and the database checks) are the rule.
// Row-level security decides whether this repository is yours; the database records who saved.
export async function saveSettings(formData: FormData) {
  await requireViewer();
  const repoId = parseId(String(formData.get("repo_id") ?? ""));
  if (!repoId) redirect("/dashboard");
  const back = `/dashboard/repos/${repoId}/settings`;

  const picked = formData.getAll("scanners").map(String);
  const scanners = SCANNERS.filter((name) => picked.includes(name));
  const severity = SEVERITIES.find((s) => s === formData.get("report_min_severity"));
  const order = LLM_ORDERS.find((o) => o.join(",") === formData.get("llm_order"));
  if (scanners.length === 0) redirect(`${back}?error=no-scanner`);
  if (!severity || !order) redirect(`${back}?error=invalid`);

  const supabase = await createClient();
  const { error } = await supabase
    .from("repo_settings")
    .upsert({ repo_id: repoId, scanners, report_min_severity: severity, llm_order: order }, { onConflict: "repo_id" });
  if (error) redirect(`${back}?error=${error.code === "42501" ? "denied" : "failed"}`);

  revalidatePath(back);
  redirect(`${back}?saved=1`);
}
