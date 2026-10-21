create or replace function public.app_jobs(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin', 'caller']);
begin
  return (select coalesce(json_agg(j order by j.id desc), '[]'::json) from (
    select s.id, s.country, s.city, s.category, s.status, s.found, s.added, s.message, s.created_at, s.started_at,
           s.finished_at
      from public.search_jobs s order by s.id desc limit 40) j);
end $$;

create or replace function public.worker_report(p_code text, p_since timestamptz, p_limit int default 60, p_mark boolean default true)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare picked uuid[]; result json;
begin
  select array_agg(x.id) into picked from (
    select l.id from public.leads l
     where l.emailed_at is null and l.stage = 'new' and l.priority in (1, 2) and l.phone_intl is not null
       and (l.priority = 2 or l.checked_at is not null)
     order by l.priority, l.verified desc, l.score desc
     limit least(greatest(p_limit, 1), 500)) x;

  select json_build_object(
    'leads', (select coalesce(json_agg(l order by l.priority, l.verified desc, l.score desc), '[]'::json) from (
                select id, name, category, subcategory, country, city, locality, address, lat, lon, phone, phone_intl,
                       email, website, socials, website_status, issues, verified, priority, score
                  from public.leads where id = any(coalesce(picked, '{}'))) l),
    'callbacks', (select coalesce(json_agg(c order by c.callback_at), '[]'::json) from (
                select name, phone, phone_intl, city, notes, callback_at from public.leads
                 where stage = 'callback' and callback_at < now() + interval '1 day') c),
    'new_found', (select count(*) from public.leads where created_at >= p_since),
    'checked', (select count(*) from public.leads where checked_at >= p_since),
    'jobs', (select coalesce(json_agg(j order by j.id), '[]'::json) from (
                select s.id, s.city, s.country, s.category, s.status, s.found, s.added, s.message
                  from public.search_jobs s where s.finished_at >= p_since) j),
    'totals', json_build_object(
        'no_website', (select count(*) from public.leads where priority = 1 and stage = 'new'),
        'improve_website', (select count(*) from public.leads where priority = 2 and stage = 'new'),
        'not_emailed', (select count(*) from public.leads where emailed_at is null and stage = 'new' and priority in (1, 2)),
        'unchecked', (select count(*) from public.leads where checked_at is null and stage = 'new' and priority in (1, 2)),
        'interested', (select count(*) from public.leads where stage = 'interested'),
        'won', (select count(*) from public.leads where stage = 'won'))
  ) into result;

  if p_mark and picked is not null then
    update public.leads set emailed_at = now() where id = any(picked);
  end if;
  return result;
end $$;
