-- The morning worker timed out (statement timeout, 3 s for the worker's role) once leads passed ~200k rows:
-- worker_refresh_learning scanned every lead to find the few that were called, and worker_rescore_some
-- scanned every open lead to find the (usually zero) whose learned adjustment is out of date.

-- only called leads: tiny index, makes the learning refresh instant
create index if not exists leads_called_idx on public.leads (country, category) where call_count > 0;

-- open leads by shop type and the adjustment they were scored with
create index if not exists leads_rescore_idx on public.leads (country, category, learn_adj)
  where stage in ('new', 'callback');

-- per shop type, look only for leads scored with a different adjustment (two index range scans, no full scan)
create or replace function public.worker_rescore_some(p_code text, p_limit int default 1500)
returns int language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare n int; lim int := least(greatest(p_limit, 1), 3000);
begin
  update public.leads l set updated_at = now()
   where l.id in (
     select x.id from public.category_stats cs
     cross join lateral (
       (select l2.id from public.leads l2
         where l2.country = cs.country and l2.category = cs.category
           and l2.stage in ('new', 'callback') and l2.learn_adj < cs.adjust limit lim)
       union all
       (select l2.id from public.leads l2
         where l2.country = cs.country and l2.category = cs.category
           and l2.stage in ('new', 'callback') and l2.learn_adj > cs.adjust limit lim)
     ) x
     limit lim);
  get diagnostics n = row_count;
  return n;
end $$;
revoke all on function public.worker_rescore_some(text, int) from public;
grant execute on function public.worker_rescore_some(text, int) to anon, authenticated;
