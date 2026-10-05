-- Week 8: say *why* a requested fix ended without a patch.
-- A fixed word chosen by the worker, never free text: nothing a model or a repository wrote reaches the dashboard.

alter table public.fix_requests
  add column reason text check (reason in (
    'secret', 'false_positive', 'prompt_injection', 'too_large', 'not_a_file', 'model_declined',
    'patch_rejected', 'new_findings', 'still_reported', 'broken_patch',
    'ai_unavailable', 'ai_bad_answer', 'error', 'other'
  ));

-- Same trigger as before, and a retry also forgets the old reason.
create or replace function public.stamp_fix_request() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.status = 'queued' then
    new.requested_by := coalesce(auth.uid(), old.requested_by, new.requested_by);
    new.requested_at := now();
    new.fix_id := null;
    new.reason := null;
    new.finished_at := null;
  end if;
  return new;
end;
$$;
