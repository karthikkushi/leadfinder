create or replace function public.app_login(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin','caller']);
begin
  return json_build_object('id', m.id, 'name', m.name, 'role', m.role);
end $$;

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
       l.verified desc,
       l.score desc,
       l.name asc
     limit least(greatest(p_limit, 1), 200) offset greatest(p_offset, 0)
  ) r;
  return result;
end $$;

create or replace function public.app_update_lead(
  p_code text, p_id uuid, p_outcome text, p_note text default null, p_callback_at timestamptz default null)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin','caller']);
declare new_stage text;
begin
  new_stage := case p_outcome
    when 'no_answer' then 'new'
    when 'callback' then 'callback'
    when 'interested' then 'interested'
    when 'not_interested' then 'not_interested'
    when 'won' then 'won'
    when 'wrong_number' then 'wrong_number'
    when 'do_not_call' then 'do_not_call'
    when 'has_website' then 'skip'
    when 'reopen' then 'new'
    when 'note' then null
    else null end;
  if new_stage is null and p_outcome <> 'note' then
    raise exception 'Unknown outcome %', p_outcome;
  end if;
  if p_outcome = 'callback' and p_callback_at is null then
    raise exception 'Pick a callback time';
  end if;

  update public.leads l set
    stage = coalesce(new_stage, l.stage),
    callback_at = case when p_outcome = 'callback' then p_callback_at
                       when p_outcome = 'note' then l.callback_at else null end,
    notes = case when p_note is not null and length(trim(p_note)) > 0
                 then trim(p_note) else l.notes end,
    last_outcome = case when p_outcome in ('note', 'reopen') then l.last_outcome else p_outcome end,
    last_called_at = case when p_outcome in ('note', 'reopen') then l.last_called_at else now() end,
    call_count = l.call_count + case when p_outcome in ('note', 'reopen', 'has_website') then 0 else 1 end,
    called_by = case when p_outcome in ('note', 'reopen') then l.called_by else m.id end,
    updated_at = now()
  where l.id = p_id;
  if not found then raise exception 'Lead not found'; end if;

  insert into public.call_log (lead_id, member_id, outcome, note) values (p_id, m.id, p_outcome, nullif(trim(coalesce(p_note, '')), ''));
  return json_build_object('ok', true, 'stage', (select stage from public.leads where id = p_id));
end $$;

create or replace function public.app_options(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin','caller']);
begin
  return json_build_object(
    'places', (select coalesce(json_agg(x order by x.country, x.city), '[]'::json) from (
                 select country, city, count(*) as n from public.leads group by 1, 2) x),
    'categories', (select coalesce(json_agg(distinct category), '[]'::json) from public.leads));
end $$;

create or replace function public.app_stats(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin','caller']);
begin
  return json_build_object(
    'total', (select count(*) from public.leads),
    'to_call', (select count(*) from public.leads where stage = 'new' and priority in (1, 2) and phone_intl is not null),
    'no_website', (select count(*) from public.leads where priority = 1 and stage = 'new'),
    'improve_website', (select count(*) from public.leads where priority = 2 and stage = 'new'),
    'unchecked', (select count(*) from public.leads where checked_at is null and priority in (1, 2)),
    'callbacks_due', (select count(*) from public.leads where stage = 'callback' and callback_at <= now() + interval '1 day'),
    'by_stage', (select coalesce(json_object_agg(stage, n), '{}'::json) from (select stage, count(*) n from public.leads group by 1) s),
    'calls_today', (select count(*) from public.call_log where created_at >= date_trunc('day', now() at time zone 'Asia/Kolkata') at time zone 'Asia/Kolkata'),
    'by_member_today', (select coalesce(json_agg(x), '[]'::json) from (
        select t.name, count(c.id) n from public.call_log c join public.team t on t.id = c.member_id
         where c.created_at >= date_trunc('day', now() at time zone 'Asia/Kolkata') at time zone 'Asia/Kolkata'
         group by t.name order by n desc) x),
    'by_place', (select coalesce(json_agg(x order by x.country, x.city), '[]'::json) from (
        select country, city, count(*) total,
               count(*) filter (where priority = 1 and stage = 'new') p1,
               count(*) filter (where priority = 2 and stage = 'new') p2,
               count(*) filter (where stage = 'won') won
          from public.leads group by 1, 2) x),
    'db_mb', (select round(pg_database_size(current_database()) / 1048576.0)));
end $$;

create or replace function public.app_queue_job(p_code text, p_country text, p_city text, p_category text default 'all')
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin']);
declare jid bigint;
begin
  if coalesce(trim(p_city), '') = '' or coalesce(trim(p_country), '') = '' then
    raise exception 'Pick a country and a city';
  end if;
  select id into jid from public.search_jobs
   where status in ('queued', 'running') and country = p_country and lower(city) = lower(trim(p_city))
     and category = coalesce(p_category, 'all');
  if jid is null then
    insert into public.search_jobs (country, city, category, requested_by)
    values (p_country, initcap(trim(p_city)), coalesce(p_category, 'all'), m.id) returning id into jid;
  end if;
  return json_build_object('id', jid);
end $$;

create or replace function public.app_jobs(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin', 'caller']);
begin
  return (select coalesce(json_agg(j order by j.id desc), '[]'::json) from (
    select id, country, city, category, status, found, added, message, created_at, started_at, finished_at
      from public.search_jobs order by id desc limit 40) j);
end $$;

create or replace function public.app_add_member(p_code text, p_name text, p_role text default 'caller')
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin']);
declare new_code text := encode(extensions.gen_random_bytes(12), 'hex');
begin
  if p_role not in ('admin', 'caller') then raise exception 'Role must be admin or caller'; end if;
  if coalesce(trim(p_name), '') = '' then raise exception 'Enter a name'; end if;
  insert into public.team (name, role, code_hash)
  values (trim(p_name), p_role, encode(extensions.digest(new_code, 'sha256'), 'hex'));
  return json_build_object('code', new_code);
end $$;

create or replace function public.app_members(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin']);
begin
  return (select coalesce(json_agg(x order by x.created_at), '[]'::json) from (
    select t.id, t.name, t.role, t.active, t.created_at,
           (select count(*) from public.call_log c where c.member_id = t.id) as calls,
           (select count(*) from public.leads l where l.called_by = t.id and l.stage = 'won') as won
      from public.team t where t.role <> 'worker') x);
end $$;

create or replace function public.app_set_member_active(p_code text, p_id uuid, p_active boolean)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin']);
begin
  if p_id = m.id then raise exception 'You cannot switch off your own access'; end if;
  update public.team set active = p_active where id = p_id and role <> 'worker';
  return json_build_object('ok', found);
end $$;

-- Worker functions (the agents)
create or replace function public.worker_claim_job(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare j public.search_jobs;
begin
  update public.search_jobs set status = 'queued', message = 'restarted after a stopped run'
   where status = 'running' and started_at < now() - interval '90 minutes';
  update public.search_jobs s set status = 'running', started_at = now(), message = null
   where s.id = (select id from public.search_jobs where status = 'queued'
                  order by created_at limit 1 for update skip locked)
  returning * into j;
  if j.id is null then return null; end if;
  return row_to_json(j);
end $$;

create or replace function public.worker_finish_job(p_code text, p_id bigint, p_status text, p_found int, p_added int, p_message text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
begin
  update public.search_jobs set status = p_status, found = p_found, added = p_added,
         message = left(p_message, 500), finished_at = now()
   where id = p_id;
  return json_build_object('ok', found);
end $$;

create or replace function public.worker_upsert_leads(p_code text, p_rows jsonb)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare n_ins int; n_upd int;
begin
  with src as (
    select * from jsonb_to_recordset(p_rows) as r(
      source_key text, sources text[], name text, category text, subcategory text, country text, city text,
      locality text, address text, lat double precision, lon double precision, phone text, phone_intl text,
      email text, website text, socials text[], website_status text, issues text[], priority smallint, score int)
  ), fresh as (
    select s.* from src s
     where s.phone_intl is null or not exists (
       select 1 from public.leads l where l.phone_intl = s.phone_intl and l.city = s.city and l.source_key <> s.source_key)
  ), up as (
    insert into public.leads as l (source_key, sources, name, category, subcategory, country, city, locality, address,
                                   lat, lon, phone, phone_intl, email, website, socials, website_status, issues, priority, score)
    select source_key, coalesce(sources, '{}'), name, category, subcategory, country, city, locality, address,
           lat, lon, phone, phone_intl, email, website, coalesce(socials, '{}'), coalesce(website_status, 'unknown'),
           coalesce(issues, '{}'), coalesce(priority, 1), coalesce(score, 0)
      from fresh
    on conflict (source_key) do update set
      sources = excluded.sources, name = excluded.name, subcategory = excluded.subcategory,
      locality = coalesce(excluded.locality, l.locality), address = coalesce(excluded.address, l.address),
      phone = coalesce(l.phone, excluded.phone), phone_intl = coalesce(l.phone_intl, excluded.phone_intl),
      email = coalesce(l.email, excluded.email),
      socials = (select array(select distinct unnest(l.socials || excluded.socials))),
      updated_at = now()
    returning (xmax = 0) as inserted
  )
  select count(*) filter (where inserted), count(*) filter (where not inserted) into n_ins, n_upd from up;
  return json_build_object('inserted', n_ins, 'updated', n_upd);
end $$;

create or replace function public.worker_next_checks(p_code text, p_limit int default 40)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare result json;
begin
  with picked as (
    select id from public.leads
     where checked_at is null and stage = 'new' and priority in (1, 2)
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

create or replace function public.worker_save_checks(p_code text, p_rows jsonb)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare n int;
begin
  update public.leads l set
    website = coalesce(r.website, l.website),
    socials = (select array(select distinct unnest(l.socials || coalesce(r.socials, '{}')))),
    email = coalesce(l.email, r.email),
    website_status = r.website_status,
    issues = coalesce(r.issues, '{}'),
    priority = r.priority,
    score = r.score,
    verified = coalesce(r.verified, true),
    checked_at = now(),
    updated_at = now()
  from jsonb_to_recordset(p_rows) as r(id uuid, website text, socials text[], email text, website_status text,
                                       issues text[], priority smallint, score int, verified boolean)
  where l.id = r.id;
  get diagnostics n = row_count;
  return json_build_object('updated', n);
end $$;

-- only the API roles may call these, and each one checks the access code itself
do $$
declare f text;
begin
  for f in select p.oid::regprocedure::text from pg_proc p join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public' and (p.proname like 'app\_%' or p.proname like 'worker\_%')
  loop
    execute format('revoke all on function %s from public', f);
    execute format('grant execute on function %s to anon, authenticated', f);
  end loop;
end $$;
