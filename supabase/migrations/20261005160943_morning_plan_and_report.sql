alter table public.leads add column if not exists emailed_at timestamptz;
create index if not exists leads_not_emailed_idx on public.leads (priority, verified, score desc)
  where emailed_at is null and stage = 'new';

-- Morning planner: when nothing is queued and the checking backlog is small, queue the next city on the list
-- that hasn't been scanned in p_days days.
create or replace function public.worker_plan(p_code text, p_targets jsonb, p_days int default 30, p_backlog int default 1500)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare t record; jid bigint; backlog int;
begin
  if exists (select 1 from public.search_jobs where status in ('queued', 'running')) then
    return json_build_object('queued', null, 'reason', 'jobs already waiting');
  end if;
  select count(*) into backlog from public.leads where checked_at is null and stage = 'new' and priority in (1, 2);
  if backlog >= p_backlog then
    return json_build_object('queued', null, 'reason', format('%s leads still to check first', backlog));
  end if;
  for t in select x.country, x.city from jsonb_to_recordset(p_targets) as x(country text, city text) loop
    if not exists (select 1 from public.search_jobs j
                    where j.country = t.country and lower(j.city) = lower(t.city)
                      and j.status = 'done' and j.finished_at > now() - make_interval(days => p_days)) then
      insert into public.search_jobs (country, city, category) values (t.country, t.city, 'all') returning id into jid;
      return json_build_object('queued', jid, 'country', t.country, 'city', t.city);
    end if;
  end loop;
  return json_build_object('queued', null, 'reason', 'every target city scanned recently');
end $$;

-- Morning email: the best leads not emailed before, today's callbacks, and run totals. Marks the leads as emailed.
create or replace function public.worker_report(p_code text, p_since timestamptz, p_limit int default 60, p_mark boolean default true)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare picked uuid[]; result json;
begin
  select array_agg(id) into picked from (
    select id from public.leads
     where emailed_at is null and stage = 'new' and priority in (1, 2) and phone_intl is not null
       and (priority = 2 or checked_at is not null)
     order by priority, verified desc, score desc
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
                select city, country, category, status, found, added, message from public.search_jobs
                 where finished_at >= p_since) j),
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

revoke all on function public.worker_plan(text, jsonb, int, int) from public;
grant execute on function public.worker_plan(text, jsonb, int, int) to anon, authenticated;
revoke all on function public.worker_report(text, timestamptz, int, boolean) from public;
grant execute on function public.worker_report(text, timestamptz, int, boolean) to anon, authenticated;
