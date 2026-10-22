create or replace function public.worker_mark_emailed(p_code text, p_ids uuid[])
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare n int;
begin
  update public.leads set emailed_at = now() where id = any(p_ids) and emailed_at is null;
  get diagnostics n = row_count;
  return json_build_object('marked', n);
end $$;
revoke all on function public.worker_mark_emailed(text, uuid[]) from public;
grant execute on function public.worker_mark_emailed(text, uuid[]) to anon, authenticated;
