-- Week 8: ask for a fix from the dashboard.
-- The browser only says "this issue, please". Everything the worker needs (code, commit, findings) comes from rows
-- the worker wrote itself, so nothing typed in the browser reaches the model or the sandbox.

create table public.fix_requests (
  id bigint generated always as identity primary key,
  issue_id bigint not null unique references public.issues (id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued', 'working', 'waiting', 'refused', 'no_fix', 'not_verified', 'failed')),
  fix_id text references public.fixes (id) on delete set null,
  requested_by uuid not null default auth.uid() references auth.users (id),
  requested_at timestamptz not null default now(),
  finished_at timestamptz
);

create index on public.fix_requests (status, requested_at);

-- A retry (status back to 'queued') starts clean, and who asked is recorded by the database.
-- The worker (no auth.uid()) keeps the original requester.
create function public.stamp_fix_request() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.status = 'queued' then
    new.requested_by := coalesce(auth.uid(), old.requested_by, new.requested_by);
    new.requested_at := now();
    new.fix_id := null;
    new.finished_at := null;
  end if;
  return new;
end;
$$;

create trigger stamp_fix_request before insert or update on public.fix_requests
  for each row execute function public.stamp_fix_request();

alter table public.fix_requests enable row level security;

-- First lock: signed-in users may read, insert only issue_id, and update only status. Visitors get nothing.
revoke all on public.fix_requests from anon, authenticated;
grant select on public.fix_requests to authenticated;
grant insert (issue_id) on public.fix_requests to authenticated;
grant update (status) on public.fix_requests to authenticated;

create policy "owners read their fix requests" on public.fix_requests
  for select to authenticated
  using (issue_id in (
    select i.id from public.issues i join public.scans s on s.id = i.scan_id join public.repos r on r.id = s.repo_id
    where r.owner_id = (select auth.uid())
  ));

-- Second lock: only your own issues, from a finished scan, and never an issue the worker would refuse anyway
-- (a leaked secret must be rotated by a person; a false positive needs no patch).
create policy "owners request fixes for their fixable issues" on public.fix_requests
  for insert to authenticated
  with check (
    status = 'queued'
    and issue_id in (
      select i.id from public.issues i join public.scans s on s.id = i.scan_id join public.repos r on r.id = s.repo_id
      where r.owner_id = (select auth.uid())
        and s.status = 'done'
        and not i.false_positive
        and not i.findings @> '[{"tool": "gitleaks"}]'::jsonb
    )
  );

-- Retry: only a request that ended without a patch, and only back to 'queued'.
create policy "owners retry their unfinished fix requests" on public.fix_requests
  for update to authenticated
  using (
    status in ('failed', 'no_fix', 'not_verified')
    and issue_id in (
      select i.id from public.issues i join public.scans s on s.id = i.scan_id join public.repos r on r.id = s.repo_id
      where r.owner_id = (select auth.uid())
    )
  )
  with check (status = 'queued');
