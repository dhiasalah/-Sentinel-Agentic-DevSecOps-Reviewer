import Link from "next/link";
import type { ReactNode } from "react";

type Crumb = { href: string; label: string };

// The label column + title used by every dashboard page.
export function PageIntro({ label, crumbs = [], children }: { label: string; crumbs?: Crumb[]; children: ReactNode }) {
  return (
    <div className="grid gap-x-8 gap-y-3 lg:grid-cols-12">
      <p className="font-mono text-[12px] tracking-[0.08em] text-muted uppercase lg:col-span-3 lg:pt-3">{label}</p>
      <div className="min-w-0 lg:col-span-9">
        {crumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-x-2 text-[13px] text-muted">
            {crumbs.map((crumb) => (
              <span key={crumb.href} className="inline-flex items-center gap-2">
                <Link href={crumb.href} className="hover:text-ink">
                  {crumb.label}
                </Link>
                <span aria-hidden="true">/</span>
              </span>
            ))}
          </nav>
        )}
        {children}
      </div>
    </div>
  );
}

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-14 grid gap-x-8 gap-y-4 lg:grid-cols-12">
      <div className="lg:col-span-3">
        <h2 className="font-serif text-[21px] leading-tight">{title}</h2>
        {aside && <div className="mt-1 text-[13px] text-muted">{aside}</div>}
      </div>
      <div className="min-w-0 lg:col-span-9">{children}</div>
    </section>
  );
}
