-- Leads of one city, page by page, for the feature agent.
create or replace function public.worker_city_leads(p_code text, p_country text, p_city text, p_after uuid default null, p_limit int default 5000)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
begin
  return (select coalesce(json_agg(x order by x.id), '[]'::json) from (
    select id, source_key, name, category, lat, lon, phone_intl, email, socials
      from public.leads
     where country = p_country and city = p_city and (p_after is null or id > p_after)
     order by id limit least(greatest(p_limit, 1), 5000)) x);
end $$;

create or replace function public.worker_save_features(p_code text, p_rows jsonb)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare n int;
begin
  update public.leads l set
    confidence = r.confidence, phone_type = r.phone_type, rivals_nearby = r.rivals_nearby,
    rivals_with_site = r.rivals_with_site, brands_nearby = r.brands_nearby,
    has_instagram = coalesce(r.has_instagram, false), branches = r.branches, features_at = now()
  from jsonb_to_recordset(p_rows) as r(id uuid, confidence real, phone_type text, rivals_nearby int,
                                       rivals_with_site int, brands_nearby int, has_instagram boolean, branches int)
  where l.id = r.id;
  get diagnostics n = row_count;
  return json_build_object('updated', n);
end $$;

-- Learning: compare each shop type's "yes" rate with the overall rate (needs 5+ finished calls to count).
create or replace function public.worker_refresh_learning(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare base real; changed int := 0;
begin
  create temp table s on commit drop as
    select l.country, l.category,
           count(*) filter (where l.last_outcome in ('interested', 'won', 'not_interested', 'has_website')) as calls,
           count(*) filter (where l.stage in ('interested', 'won')) as positive
      from public.leads l where l.call_count > 0 group by 1, 2;
  select coalesce(sum(positive)::real / nullif(sum(calls), 0), 0.1) into base from s;
  base := greatest(base, 0.05);
  with calc as (
    select country, category, calls, positive,
           case when calls < 5 then 0
                else greatest(-10, least(10, round(((positive + 10 * base) / (calls + 10) - base) / base * 10)))::int end as adjust
      from s
  ), up as (
    insert into public.category_stats as cs (country, category, calls, positive, adjust, updated_at)
    select country, category, calls, positive, adjust, now() from calc
    on conflict (country, category) do update set calls = excluded.calls, positive = excluded.positive,
      adjust = excluded.adjust, updated_at = now()
    returning cs.country, cs.category, cs.adjust
  )
  select count(*) into changed from up;
  -- re-score open leads so the new adjustments apply
  update public.leads l set updated_at = now()
    from public.category_stats cs
   where cs.country = l.country and cs.category = l.category and l.stage in ('new', 'callback') and cs.updated_at > now() - interval '1 minute';
  return json_build_object('categories', changed, 'base_rate', base);
end $$;

drop function if exists public.worker_next_checks(text, int, int, text);
create or replace function public.worker_next_checks(p_code text, p_limit int default 40, p_priority int default null,
                                                     p_country text default null)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare result json;
begin
  with picked as (
    select id from public.leads
     where checked_at is null and stage = 'new' and priority in (1, 2) and tier <> 'X'
       and (p_priority is null or priority = p_priority)
       and (p_country is null or country = p_country)
       and (check_claimed_at is null or check_claimed_at < now() - interval '30 minutes')
     order by lead_score desc
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

drop function if exists public.worker_report(text, timestamptz, int, boolean, text[]);
create or replace function public.worker_report(p_code text, p_since timestamptz, p_limit int default 10,
                                                p_mark boolean default true, p_countries text[] default null)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare picked uuid[]; result json;
begin
  select array_agg(x.id) into picked from (
    select l.id from public.leads l
     where l.emailed_at is null and l.stage = 'new' and l.priority in (1, 2) and l.phone_intl is not null
       and l.checked_at is not null and l.tier in ('A', 'B', 'C')
       and (p_countries is null or l.country = any(p_countries))
     order by l.lead_score desc
     limit least(greatest(p_limit, 1), 500)) x;

  select json_build_object(
    'leads', (select coalesce(json_agg(l order by l.lead_score desc), '[]'::json) from (
                select id, name, category, subcategory, country, city, locality, address, lat, lon, phone, phone_intl,
                       email, website, socials, website_status, issues, verified, priority, score, lead_score, tier, reasons
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
        'tier_a', (select count(*) from public.leads where tier = 'A' and stage = 'new'
                     and (p_countries is null or country = any(p_countries))),
        'tier_b', (select count(*) from public.leads where tier = 'B' and stage = 'new'
                     and (p_countries is null or country = any(p_countries))),
        'no_website', (select count(*) from public.leads where priority = 1 and stage = 'new' and tier <> 'X'
                         and (p_countries is null or country = any(p_countries))),
        'improve_website', (select count(*) from public.leads where priority = 2 and stage = 'new' and checked_at is not null
                         and tier <> 'X' and (p_countries is null or country = any(p_countries))),
        'interested', (select count(*) from public.leads where stage = 'interested'),
        'won', (select count(*) from public.leads where stage = 'won'))
  ) into result;

  if p_mark and picked is not null then
    update public.leads set emailed_at = now() where id = any(picked);
  end if;
  return result;
end $$;

do $$
declare f text;
begin
  for f in select p.oid::regprocedure::text from pg_proc p join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public' and p.proname in ('worker_city_leads', 'worker_save_features',
                  'worker_refresh_learning', 'worker_next_checks', 'worker_report')
  loop
    execute format('revoke all on function %s from public', f);
    execute format('grant execute on function %s to anon, authenticated', f);
  end loop;
end $$;
