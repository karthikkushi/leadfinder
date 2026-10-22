drop function if exists public.worker_next_checks(text, int, int);
create or replace function public.worker_next_checks(p_code text, p_limit int default 40, p_priority int default null,
                                                     p_country text default null)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare result json;
begin
  with picked as (
    select id from public.leads
     where checked_at is null and stage = 'new' and priority in (1, 2)
       and (p_priority is null or priority = p_priority)
       and (p_country is null or country = p_country)
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
revoke all on function public.worker_next_checks(text, int, int, text) from public;
grant execute on function public.worker_next_checks(text, int, int, text) to anon, authenticated;

drop function if exists public.worker_report(text, timestamptz, int, boolean);
create or replace function public.worker_report(p_code text, p_since timestamptz, p_limit int default 60,
                                                p_mark boolean default true, p_countries text[] default null)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare picked uuid[]; result json;
begin
  select array_agg(x.id) into picked from (
    select l.id from public.leads l
     where l.emailed_at is null and l.stage = 'new' and l.priority in (1, 2) and l.phone_intl is not null
       and (l.priority = 2 or l.checked_at is not null)
       and (p_countries is null or l.country = any(p_countries))
     order by l.priority, l.verified desc, l.score desc
     limit least(greatest(p_limit, 1), 500)) x;

  select json_build_object(
    'leads', (select coalesce(json_agg(l order by l.priority, l.verified desc, l.score desc), '[]'::json) from (
                select id, name, category, subcategory, country, city, locality, address, lat, lon, phone, phone_intl,
                       email, website, socials, website_status, issues, verified, priority, score
                  from public.leads where id = any(coalesce(picked, '{}'))) l),
    'callbacks', (select coalesce(json_agg(c order by c.callback_at), '[]'::json) from (
                select name, phone, phone_intl, city, notes, callback_at from public.leads
                 where stage = 'callback' and callback_at < now() + interval '1 day'
                   and (p_countries is null or country = any(p_countries))) c),
    'new_found', (select count(*) from public.leads where created_at >= p_since
                    and (p_countries is null or country = any(p_countries))),
    'checked', (select count(*) from public.leads where checked_at >= p_since
                    and (p_countries is null or country = any(p_countries))),
    'jobs', (select coalesce(json_agg(j order by j.id), '[]'::json) from (
                select s.id, s.city, s.country, s.category, s.status, s.found, s.added, s.message
                  from public.search_jobs s where s.finished_at >= p_since
                   and (p_countries is null or s.country = any(p_countries))) j),
    'totals', json_build_object(
        'no_website', (select count(*) from public.leads where priority = 1 and stage = 'new'
                         and (p_countries is null or country = any(p_countries))),
        'improve_website', (select count(*) from public.leads where priority = 2 and stage = 'new'
                         and (p_countries is null or country = any(p_countries))),
        'not_emailed', (select count(*) from public.leads where emailed_at is null and stage = 'new' and priority in (1, 2)
                         and (p_countries is null or country = any(p_countries))),
        'unchecked', (select count(*) from public.leads where checked_at is null and stage = 'new' and priority in (1, 2)
                         and (p_countries is null or country = any(p_countries))),
        'interested', (select count(*) from public.leads where stage = 'interested'),
        'won', (select count(*) from public.leads where stage = 'won'))
  ) into result;

  if p_mark and picked is not null then
    update public.leads set emailed_at = now() where id = any(picked);
  end if;
  return result;
end $$;
revoke all on function public.worker_report(text, timestamptz, int, boolean, text[]) from public;
grant execute on function public.worker_report(text, timestamptz, int, boolean, text[]) to anon, authenticated;

-- the app's lead list and city list can be limited to one country
drop function if exists public.app_leads(text, text, text, text, text, int, text, int, int);
create or replace function public.app_leads(
  p_code text, p_view text default 'to_call', p_country text default null, p_city text default null,
  p_category text default null, p_priority int default null, p_search text default null,
  p_limit int default 50, p_offset int default 0)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin','caller']);
declare result json;
begin
  select coalesce(json_agg(r), '[]'::json) into result from (
    select l.id, l.name, l.category, l.subcategory, l.country, l.city, l.locality, l.address, l.lat, l.lon,
           l.phone, l.phone_intl, l.email, l.website, l.socials, l.website_status, l.issues, l.verified,
           l.priority, l.score, l.stage, l.callback_at, l.notes, l.last_outcome, l.last_called_at, l.call_count
      from public.leads l
     where (p_country is null or l.country = p_country)
       and (p_city is null or l.city = p_city)
       and (p_category is null or l.category = p_category)
       and (p_priority is null or l.priority = p_priority)
       and (p_search is null or l.name ilike '%' || p_search || '%' or l.phone_intl like '%' || p_search || '%'
            or l.locality ilike '%' || p_search || '%')
       and case p_view
             when 'to_call' then l.stage = 'new' and l.priority in (1, 2) and l.phone_intl is not null
             when 'callbacks' then l.stage = 'callback'
             when 'interested' then l.stage = 'interested'
             when 'won' then l.stage = 'won'
             when 'done' then l.stage in ('not_interested', 'wrong_number', 'do_not_call', 'skip')
             else true
           end
     order by
       case when p_view = 'callbacks' then extract(epoch from l.callback_at) end asc nulls last,
       case when p_view in ('interested', 'won', 'done') then extract(epoch from l.updated_at) end desc nulls last,
       l.priority asc,
       (l.last_called_at is not null) asc,
       (l.checked_at is not null) desc,
       l.verified desc,
       l.score desc,
       l.name asc
     limit least(greatest(p_limit, 1), 200) offset greatest(p_offset, 0)
  ) r;
  return result;
end $$;
revoke all on function public.app_leads(text, text, text, text, text, int, text, int, int) from public;
grant execute on function public.app_leads(text, text, text, text, text, int, text, int, int) to anon, authenticated;
