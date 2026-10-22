drop function if exists public.worker_next_checks(text, int);
create or replace function public.worker_next_checks(p_code text, p_limit int default 40, p_priority int default null)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare result json;
begin
  with picked as (
    select id from public.leads
     where checked_at is null and stage = 'new' and priority in (1, 2)
       and (p_priority is null or priority = p_priority)
       and (check_claimed_at is null or check_claimed_at < now() - interval '30 minutes')
     order by priority asc, score desc
     limit least(greatest(p_limit, 1), 200)
     for update skip locked
  ), claimed as (
    update public.leads l set check_claimed_at = now() from picked where l.id = picked.id
    returning l.id, l.name, l.category, l.subcategory, l.country, l.city, l.locality, l.address, l.phone, l.phone_intl,
              l.email, l.website, l.socials, l.website_status, l.issues, l.priority, l.score
  )
  select coalesce(json_agg(claimed), '[]'::json) into result from claimed;
  return result;
end $$;
revoke all on function public.worker_next_checks(text, int, int) from public;
grant execute on function public.worker_next_checks(text, int, int) to anon, authenticated;
