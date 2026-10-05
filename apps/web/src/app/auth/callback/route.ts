import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

// GitHub → Supabase → here with a one-time ?code. Always lands on /dashboard: no "next" parameter, so no open redirect.
export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return NextResponse.redirect(new URL("/login?error=callback", request.url));
}
