create or replace function public.worker_report(p_code text, p_since timestamptz, p_limit int default 10,
                                                p_mark boolean default true, p_countries text[] default null)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare picked uuid[]; result json; today date := private.today_ist();
begin
  -- the email lists today's hot leads (the same 10 shown in the app's Today tab)
  select array_agg(x.id) into picked from (
    select l.id from public.leads l
     where l.hot_date = today and (p_countries is null or l.country = any(p_countries))
     order by l.lead_score desc limit least(greatest(p_limit, 1), 500)) x;
  if picked is null then  -- no pick today: fall back to the best checked shops not emailed before
    select array_agg(x.id) into picked from (
      select l.id from public.leads l
       where l.emailed_at is null and l.stage = 'new' and l.priority in (1, 2) and l.phone_intl is not null
         and l.checked_at is not null and l.tier in ('A', 'B', 'C')
         and (p_countries is null or l.country = any(p_countries))
       order by l.lead_score desc limit least(greatest(p_limit, 1), 500)) x;
  end if;

  select json_build_object(
    'leads', (select coalesce(json_agg(l order by l.lead_score desc), '[]'::json) from (
                select id, name, category, subcategory, country, city, locality, address, lat, lon, phone, phone_intl,
                       email, website, socials, website_status, issues, verified, priority, score, lead_score, tier, reasons
                  from public.leads where id = any(coalesce(picked, '{}'))) l),
    'callbacks', (select coalesce(json_agg(c order by c.callback_at), '[]'::json) from (
                select name, phone, phone_intl, city, notes, callback_at from public.leads
                 where stage = 'callback' and callback_at < now() + interval '1 day'
                   and (p_countries is null or country = any(p_countries))) c),
    'new_found', 0,
    'checked', (select count(*) from public.leads where checked_at >= p_since
                    and (p_countries is null or country = any(p_countries))),
    'jobs', '[]'::json,
    'totals', (select json_build_object(
        'tier_a', coalesce((sum((data->>'tier_a')::int)), 0), 'tier_b', coalesce(sum((data->>'tier_b')::int), 0),
        'no_website', coalesce(sum((data->>'no_website')::int), 0), 'improve_website', coalesce(sum((data->>'needs_work')::int), 0),
        'interested', 0, 'won', coalesce(sum((select sum((c->>'won')::int) from jsonb_array_elements(data->'cities') c)), 0))
      from public.summary_cache where p_countries is null or country = any(p_countries))
  ) into result;

  if p_mark and picked is not null then
    update public.leads set emailed_at = now() where id = any(picked);
  end if;
  return result;
end $$;
