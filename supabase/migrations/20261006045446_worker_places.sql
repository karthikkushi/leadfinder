create or replace function public.worker_places(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
begin
  return (select coalesce(json_agg(x order by x.country, x.city), '[]'::json) from (
    select country, city, count(*) as total, count(*) filter (where features_at is null) as missing
      from public.leads group by 1, 2) x);
end $$;
revoke all on function public.worker_places(text) from public;
grant execute on function public.worker_places(text) to anon, authenticated;
