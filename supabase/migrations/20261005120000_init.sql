-- Sentinel schema: repos, scans, issues, fixes, approvals.
-- Row-level security is deny by default: signed-in users read their own rows and may only insert an approval.
-- The worker writes with the secret key (service_role), which bypasses RLS.

create table public.repos (
  id bigint generated always as identity primary key,
  owner_id uuid not null references auth.users (id) on delete cascade,
  full_name text not null unique check (full_name ~ '^[A-Za-z0-9-]+/[A-Za-z0-9_.-]+$'),
  created_at timestamptz not null default now()
);

create table public.scans (
  id bigint generated always as identity primary key,
  repo_id bigint not null references public.repos (id) on delete cascade,
  pr integer not null check (pr > 0),
  head_sha text not null check (head_sha ~ '^[0-9a-f]{40}$'),
  status text not null default 'running' check (status in ('running', 'done', 'failed')),
  finding_count integer not null default 0,
  failed_scanners text[] not null default '{}',
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create table public.issues (
  id bigint generated always as identity primary key,
  scan_id bigint not null references public.scans (id) on delete cascade,
  severity text not null check (severity in ('critical', 'high', 'medium', 'low', 'info')),
  title text not null,
  explanation text not null,
  fix text not null,
  false_positive boolean not null default false,
  review_reasons text[] not null default '{}',
  findings jsonb not null default '[]'
);

create table public.fixes (
  id text primary key check (id ~ '^fix-[0-9a-f]{8}$'),
  repo_id bigint not null references public.repos (id) on delete cascade,
  pr integer not null check (pr > 0),
  head_sha text not null check (head_sha ~ '^[0-9a-f]{40}$'),
  issue_title text not null,
  summary text not null,
  provider text not null,
  diff text not null,
  patch_id text not null check (patch_id ~ '^[0-9a-f]{12}$'),
  scanners text[] not null default '{}',
  status text not null default 'waiting'
    check (status in ('waiting', 'approved', 'rejected', 'outdated', 'refused', 'not_verified', 'no_fix')),
  pr_url text,
  created_at timestamptz not null default now()
);

create table public.approvals (
  id bigint generated always as identity primary key,
  fix_id text not null unique references public.fixes (id) on delete cascade,
  decision text not null check (decision in ('approve', 'reject')),
  patch_id text not null,
  reason text not null default '' check (length(reason) <= 500),
  decided_by uuid not null default auth.uid() references auth.users (id),
  decided_at timestamptz not null default now()
);

create index on public.repos (owner_id);
create index on public.scans (repo_id, started_at desc);
create index on public.issues (scan_id);
create index on public.fixes (repo_id, created_at desc);

alter table public.repos enable row level security;
alter table public.scans enable row level security;
alter table public.issues enable row level security;
alter table public.fixes enable row level security;
alter table public.approvals enable row level security;

create policy "owners read their repos" on public.repos
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy "owners read their scans" on public.scans
  for select to authenticated
  using (repo_id in (select id from public.repos where owner_id = (select auth.uid())));

create policy "owners read their issues" on public.issues
  for select to authenticated
  using (scan_id in (
    select s.id from public.scans s join public.repos r on r.id = s.repo_id
    where r.owner_id = (select auth.uid())
  ));

create policy "owners read their fixes" on public.fixes
  for select to authenticated
  using (repo_id in (select id from public.repos where owner_id = (select auth.uid())));

create policy "owners read their approvals" on public.approvals
  for select to authenticated
  using (decided_by = (select auth.uid()));

create policy "owners decide waiting fixes once" on public.approvals
  for insert to authenticated
  with check (
    decided_by = (select auth.uid())
    and exists (
      select 1 from public.fixes f join public.repos r on r.id = f.repo_id
      where f.id = fix_id and f.status = 'waiting' and r.owner_id = (select auth.uid())
    )
  );
