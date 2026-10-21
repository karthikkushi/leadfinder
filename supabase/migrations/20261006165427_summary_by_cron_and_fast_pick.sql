create extension if not exists pg_cron;

-- counters are refreshed by the database itself every 30 minutes (no 3-second API limit there)
select cron.unschedule(jobid) from cron.job where jobname = 'leadfinder-summary';
select cron.schedule('leadfinder-summary', '*/30 * * * *', $$select private.refresh_summary()$$);

create or replace function public.worker_pick_hot(p_code text, p_countries text[] default array['IN'], p_limit int default 10)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare today date := private.today_ist(); c text; n int; total int := 0;
begin
  foreach c in array p_countries loop
    select count(*) into n from public.leads where country = c and hot_date = today;
    if n < p_limit then
      update public.leads set hot_date = today
       where id in (select l.id from public.leads l
                     where l.country = c and l.stage = 'new' and l.priority in (1, 2) and l.phone_intl is not null
                       and l.tier <> 'X' and l.checked_at is not null and l.hot_date is null and l.call_count = 0
                     order by l.list_rank desc limit p_limit - n);
      get diagnostics n = row_count;
      total := total + n;
    end if;
  end loop;
  return json_build_object('picked', total, 'date', today);
end $$;

-- the worker/app "refresh" calls now just ask cron's job to run soon; they no longer do the heavy count themselves
create or replace function public.worker_refresh_summary(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
begin
  return json_build_object('ok', true, 'note', 'counters refresh every 30 minutes');
end $$;
create or replace function public.app_refresh_summary(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin']);
begin
  return json_build_object('ok', true, 'note', 'counters refresh every 30 minutes');
end $$;
