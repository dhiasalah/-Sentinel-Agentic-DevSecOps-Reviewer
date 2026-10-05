import type { NextConfig } from "next";

// The sign-in form redirects to Supabase, which redirects to GitHub: form-action must allow both hops.
const supabaseOrigin = process.env.NEXT_PUBLIC_SUPABASE_URL ? new URL(process.env.NEXT_PUBLIC_SUPABASE_URL).origin : "";

// Sent with every response. No script-src yet: a strict CSP needs per-request nonces.
const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value: `frame-ancestors 'none'; base-uri 'self'; form-action 'self' ${supabaseOrigin} https://github.com; object-src 'none'`
      .replace(/\s+/g, " "),
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
