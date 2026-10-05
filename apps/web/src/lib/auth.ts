import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { createClient } from "@/lib/supabase/server";

export type Viewer = {
  id: string;
  login: string;
  name: string | null;
  avatarUrl: string | null;
};

// getClaims() verifies the session token's signature; the cookie alone is never trusted.
export const getViewer = cache(async (): Promise<Viewer | null> => {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const claims = data?.claims;
  if (!claims) return null;
  const meta = (claims.user_metadata ?? {}) as Record<string, unknown>;
  const text = (value: unknown) => (typeof value === "string" && value ? value : null);
  return {
    id: claims.sub,
    login: text(meta.user_name) ?? text(meta.preferred_username) ?? "unknown",
    name: text(meta.full_name) ?? text(meta.name),
    avatarUrl: text(meta.avatar_url),
  };
});

export async function requireViewer(): Promise<Viewer> {
  const viewer = await getViewer();
  if (!viewer) redirect("/login");
  return viewer;
}
