-- worker_places counted unscored leads with a full table scan and hit the 3 s statement timeout,
-- so "Scoring step failed" every morning. Counts now come from index-only scans (~0.3 s at 200k leads).
-- (also run once by hand after applying: vacuum analyze public.leads;)
create index if not exists leads_features_missing_idx on public.leads (country, city) where features_at is null;

create or replace function public.worker_places(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
begin
  return (select coalesce(json_agg(x order by x.country, x.city), '[]'::json) from (
    select t.country, t.city, t.total, coalesce(mi.missing, 0) as missing
      from (select country, city, count(*) as total from public.leads group by 1, 2) t
      left join (select country, city, count(*) as missing from public.leads where features_at is null group by 1, 2) mi
        using (country, city)) x);
end $$;
revoke all on function public.worker_places(text) from public;
grant execute on function public.worker_places(text) to anon, authenticated;
