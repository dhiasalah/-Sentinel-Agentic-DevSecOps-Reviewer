-- Week 8: live scan progress (scan_events) and per-repo settings (repo_settings).
-- Same rules as the init migration: RLS deny by default, the worker writes with the secret key.

-- One row per step of a scan ("semgrep started", "semgrep ok, 9 findings"). Structured columns only:
-- no free text, so nothing written by a model or a pull request can reach the live view.
create table public.scan_events (
  id bigint generated always as identity primary key,
  scan_id bigint not null references public.scans (id) on delete cascade,
  stage text not null check (stage in ('checkout', 'plan', 'scanner', 'triage', 'report')),
  status text not null check (status in ('started', 'ok', 'failed', 'skipped')),
  scanner text check (scanner in ('gitleaks', 'semgrep', 'trivy', 'checkov')),
  count integer check (count >= 0),
  at timestamptz not null default now()
);

create index on public.scan_events (scan_id, id);

-- Chosen by the repo owner in the dashboard, read by the worker. A missing row means "defaults".
create table public.repo_settings (
  repo_id bigint primary key references public.repos (id) on delete cascade,
  scanners text[] not null default '{gitleaks,semgrep,trivy,checkov}'
    check (scanners <@ '{gitleaks,semgrep,trivy,checkov}'::text[] and cardinality(scanners) between 1 and 4),
  report_min_severity text not null default 'info'
    check (report_min_severity in ('critical', 'high', 'medium', 'low', 'info')),
  llm_order text[] not null default '{gemini,groq}'
    check (llm_order in ('{gemini,groq}'::text[], '{groq,gemini}'::text[])),
  updated_by uuid references auth.users (id),
  updated_at timestamptz not null default now()
);

-- Who changed the settings is recorded by the database, never taken from the request.
create function public.stamp_repo_settings() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_by := auth.uid();
  new.updated_at := now();
  return new;
end;
$$;

create trigger stamp_repo_settings before insert or update on public.repo_settings
  for each row execute function public.stamp_repo_settings();

alter table public.scan_events enable row level security;
alter table public.repo_settings enable row level security;

-- Grants are the first lock, RLS the second. Supabase grants everything by default: take it back,
-- then give signed-in users only what the dashboard needs. Visitors who are not signed in get nothing.
revoke all on public.scan_events, public.repo_settings from anon, authenticated;
grant select on public.scan_events to authenticated;
grant select, insert, update on public.repo_settings to authenticated;

create policy "owners read their scan events" on public.scan_events
  for select to authenticated
  using (scan_id in (
    select s.id from public.scans s join public.repos r on r.id = s.repo_id
    where r.owner_id = (select auth.uid())
  ));

create policy "owners read their repo settings" on public.repo_settings
  for select to authenticated
  using (repo_id in (select id from public.repos where owner_id = (select auth.uid())));

create policy "owners create their repo settings" on public.repo_settings
  for insert to authenticated
  with check (repo_id in (select id from public.repos where owner_id = (select auth.uid())));

-- using: which existing rows you may touch; with check: what the row may become (no moving it to someone else's repo).
create policy "owners change their repo settings" on public.repo_settings
  for update to authenticated
  using (repo_id in (select id from public.repos where owner_id = (select auth.uid())))
  with check (repo_id in (select id from public.repos where owner_id = (select auth.uid())));
