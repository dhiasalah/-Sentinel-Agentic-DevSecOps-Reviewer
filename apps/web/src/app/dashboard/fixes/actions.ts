"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requireViewer } from "@/lib/auth";
import { isFixId } from "@/lib/data";
import { createClient } from "@/lib/supabase/server";

// The browser can only *ask*. Row-level security accepts the row only if the fix is yours and still waiting,
// the unique constraint allows one decision per fix, and the worker re-checks the patch id before acting.
export async function decide(formData: FormData) {
  await requireViewer();
  const fixId = String(formData.get("fix_id") ?? "");
  const decision = String(formData.get("decision") ?? "");
  const patchId = String(formData.get("patch_id") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();

  if (!isFixId(fixId)) redirect("/dashboard");
  const back = `/dashboard/fixes/${fixId}`;
  if (!["approve", "reject"].includes(decision) || !/^[0-9a-f]{12}$/.test(patchId) || reason.length > 500) {
    redirect(`${back}?error=invalid`);
  }

  const supabase = await createClient();
  const { error } = await supabase.from("approvals").insert({ fix_id: fixId, decision, patch_id: patchId, reason });
  if (error) {
    redirect(`${back}?error=${error.code === "23505" ? "decided" : error.code === "42501" ? "closed" : "failed"}`);
  }
  revalidatePath(back);
  revalidatePath("/dashboard");
  redirect(back);
}
