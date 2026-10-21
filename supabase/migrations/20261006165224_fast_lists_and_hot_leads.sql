-- One pre-computed sort key so the app can read leads in order straight from an index:
-- checked shops first, shops already called go to the end, then by lead score.
alter table public.leads add column if not exists hot_date date;
alter table public.leads add column if not exists list_rank int generated always as (
  lead_score + case when checked_at is not null then 1000 else 0 end
             - case when last_called_at is not null then 2000 else 0 end) stored;

create index if not exists leads_list_idx on public.leads (country, list_rank desc)
  where stage = 'new' and priority in (1, 2) and phone_intl is not null and tier <> 'X';
create index if not exists leads_list_city_idx on public.leads (country, city, list_rank desc)
  where stage = 'new' and priority in (1, 2) and phone_intl is not null and tier <> 'X';
create index if not exists leads_hot_idx on public.leads (country, hot_date) where hot_date is not null;
create index if not exists leads_stage_idx on public.leads (country, stage, updated_at desc) where stage <> 'new';
create index if not exists call_log_created_idx on public.call_log (created_at);

-- Counts that are expensive to compute on every page load, refreshed by the daily run (and on demand).
create table if not exists public.summary_cache (
  country text primary key,
  data jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.summary_cache enable row level security;
revoke all on public.summary_cache from anon, authenticated;

create or replace function private.refresh_summary()
returns void language plpgsql security definer set search_path = '' as $$
begin
  insert into public.summary_cache (country, data, updated_at)
  select x.country,
         jsonb_build_object(
           'total', sum(x.n),
           'tier_a', sum(x.a), 'tier_b', sum(x.b), 'tier_c', sum(x.c),
           'no_website', sum(x.p1), 'needs_work', sum(x.p2),
           'unchecked', sum(x.unchecked),
           'cities', jsonb_agg(jsonb_build_object('city', x.city, 'n', x.n, 'a', x.a, 'b', x.b,
                                                  'p1', x.p1, 'p2', x.p2, 'won', x.won) order by x.n desc)),
         now()
    from (select country, city, count(*) n,
                 count(*) filter (where tier = 'A' and stage = 'new') a,
                 count(*) filter (where tier = 'B' and stage = 'new') b,
                 count(*) filter (where tier = 'C' and stage = 'new') c,
                 count(*) filter (where priority = 1 and stage = 'new' and tier <> 'X') p1,
                 count(*) filter (where priority = 2 and stage = 'new' and tier <> 'X') p2,
                 count(*) filter (where checked_at is null and stage = 'new' and tier <> 'X') unchecked,
                 count(*) filter (where stage = 'won') won
            from public.leads group by 1, 2) x
   group by x.country
  on conflict (country) do update set data = excluded.data, updated_at = now();
end $$;
select private.refresh_summary();

create or replace function private.today_ist() returns date language sql stable as $$
  select (now() at time zone 'Asia/Kolkata')::date
$$;

-- App: everything the header and filters need, cheap.
create or replace function public.app_summary(p_code text, p_country text default 'IN')
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin', 'caller']);
declare today date := private.today_ist();
begin
  return json_build_object(
    'today', today,
    'hot_today', (select count(*) from public.leads where country = p_country and hot_date = today),
    'hot_done', (select count(*) from public.leads where country = p_country and hot_date = today and call_count > 0),
    'hot_earlier', (select count(*) from public.leads where country = p_country and hot_date < today and stage = 'new'),
    'callbacks_due', (select count(*) from public.leads where stage = 'callback' and country = p_country
                        and callback_at < ((today + 1)::timestamp at time zone 'Asia/Kolkata')),
    'calls_today', (select count(*) from public.call_log
                     where created_at >= (today::timestamp at time zone 'Asia/Kolkata')),
    'won', (select count(*) from public.leads where stage = 'won' and country = p_country),
    'countries', (select coalesce(json_agg(json_build_object('code', country, 'total', data->'total') order by country), '[]'::json)
                    from public.summary_cache),
    'summary', (select data from public.summary_cache where country = p_country),
    'summary_at', (select updated_at from public.summary_cache where country = p_country));
end $$;

-- App: one list function for every view, built per call so each query uses the right index.
create or replace function public.app_list(
  p_code text, p_view text default 'today', p_country text default 'IN', p_city text default null,
  p_category text default null, p_quality text default null, p_search text default null,
  p_limit int default 30, p_offset int default 0)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin', 'caller']);
declare today date := private.today_ist();
declare cond text; ord text; sql text; result json;
begin
  cond := format('l.country = %L', coalesce(p_country, 'IN'));
  case p_view
    when 'today' then
      cond := cond || format(' and l.hot_date = %L', today);
      ord := '(l.call_count > 0), l.lead_score desc';
    when 'earlier' then
      cond := cond || format(' and l.hot_date < %L and l.stage = ''new''', today);
      ord := 'l.hot_date desc, l.lead_score desc';
    when 'all' then
      cond := cond || ' and l.stage = ''new'' and l.priority in (1, 2) and l.phone_intl is not null and l.tier <> ''X''';
      ord := 'l.list_rank desc';
    when 'callbacks' then cond := cond || ' and l.stage = ''callback'''; ord := 'l.callback_at asc nulls last';
    when 'interested' then cond := cond || ' and l.stage = ''interested'''; ord := 'l.updated_at desc';
    when 'won' then cond := cond || ' and l.stage = ''won'''; ord := 'l.updated_at desc';
    when 'done' then cond := cond || ' and l.stage in (''not_interested'', ''wrong_number'', ''do_not_call'', ''skip'')';
                     ord := 'l.updated_at desc';
    else raise exception 'Unknown view %', p_view;
  end case;
  if p_city is not null then cond := cond || format(' and l.city = %L', p_city); end if;
  if p_category is not null then cond := cond || format(' and l.category = %L', p_category); end if;
  if p_quality = 'A' then cond := cond || ' and l.tier = ''A''';
  elsif p_quality = 'AB' then cond := cond || ' and l.tier in (''A'', ''B'')';
  elsif p_quality = 'nosite' then cond := cond || ' and l.priority = 1';
  elsif p_quality = 'weaksite' then cond := cond || ' and l.priority = 2';
  end if;
  if coalesce(trim(p_search), '') <> '' then
    cond := cond || format(' and (l.name ilike %L or l.locality ilike %L or l.phone_intl like %L)',
                           '%' || trim(p_search) || '%', '%' || trim(p_search) || '%', '%' || regexp_replace(p_search, '\D', '', 'g') || '%');
  end if;
  sql := format($q$
    select coalesce(json_agg(r), '[]'::json) from (
      select l.id, l.name, l.category, l.country, l.city, l.locality, l.address, l.phone, l.phone_intl, l.email,
             l.website, l.socials, l.website_status, l.issues, l.verified, l.priority, l.lead_score, l.tier, l.reasons,
             l.stage, l.callback_at, l.notes, l.last_outcome, l.last_called_at, l.call_count, l.hot_date,
             (l.checked_at is not null) as checked
        from public.leads l
       where %s
       order by %s
       limit %s offset %s) r $q$, cond, ord, least(greatest(p_limit, 1), 100), greatest(p_offset, 0));
  execute sql into result;
  return result;
end $$;

-- Daily pick: the best checked, not-yet-called shops become "today's hot leads".
create or replace function public.worker_pick_hot(p_code text, p_countries text[] default array['IN'], p_limit int default 10)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare today date := private.today_ist(); c text; n int; total int := 0;
begin
  foreach c in array p_countries loop
    select count(*) into n from public.leads where country = c and hot_date = today;
    if n < p_limit then
      update public.leads set hot_date = today
       where id in (select id from public.leads
                     where country = c and stage = 'new' and priority in (1, 2) and phone_intl is not null
                       and tier in ('A', 'B', 'C') and checked_at is not null and hot_date is null and call_count = 0
                     order by lead_score desc limit p_limit - n);
      get diagnostics n = row_count;
      total := total + n;
    end if;
  end loop;
  perform private.refresh_summary();
  return json_build_object('picked', total, 'date', today);
end $$;

create or replace function public.worker_refresh_summary(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
begin
  perform private.refresh_summary();
  return json_build_object('ok', true);
end $$;

create or replace function public.app_refresh_summary(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin']);
begin
  perform private.refresh_summary();
  return json_build_object('ok', true);
end $$;

do $$
declare f text;
begin
  for f in select p.oid::regprocedure::text from pg_proc p join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public' and p.proname in ('app_summary', 'app_list', 'worker_pick_hot',
                  'worker_refresh_summary', 'app_refresh_summary')
  loop
    execute format('revoke all on function %s from public', f);
    execute format('grant execute on function %s to anon, authenticated', f);
  end loop;
end $$;
