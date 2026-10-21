-- The daily hot-lead pick runs inside the database (pg_cron), so the app's Today tab fills even when
-- GitHub drops the scheduled run. The worker/email still calls worker_pick_hot, which tops up to the same 10.
create or replace function private.pick_hot(p_countries text[] default array['IN'], p_limit integer default 10)
returns json language plpgsql security definer set search_path to '' as $function$
declare today date := private.today_ist(); c text; n int; total int := 0;
begin
  foreach c in array p_countries loop
    select count(*) into n from public.leads where country = c and hot_date = today;
    if n < p_limit then
      -- best shops first, but at most 3 of one shop type per day so the list (and the learning) stays varied
      update public.leads set hot_date = today
       where id in (
         select id from (
           select l.id, l.list_rank,
                  row_number() over (partition by l.category order by l.list_rank desc) as nth
             from public.leads l
            where l.country = c and l.stage = 'new' and l.priority in (1, 2) and l.phone_intl is not null
              and l.tier <> 'X' and l.checked_at is not null and l.hot_date is null and l.call_count = 0) ranked
          where nth <= 3
          order by list_rank desc
          limit p_limit - n);
      get diagnostics n = row_count;
      total := total + n;
    end if;
  end loop;
  return json_build_object('picked', total, 'date', today);
end $function$;

revoke all on function private.pick_hot(text[], integer) from public, anon, authenticated;

create or replace function public.worker_pick_hot(p_code text, p_countries text[] default array['IN'], p_limit integer default 10)
returns json language plpgsql security definer set search_path to '' as $function$
declare m public.team := private.require(p_code, array['worker']);
begin
  return private.pick_hot(p_countries, p_limit);
end $function$;

-- 03:15 UTC = 08:45 India time, every day
select cron.schedule('leadfinder-hot', '15 3 * * *', $$select private.pick_hot(array['IN'], 10)$$);
