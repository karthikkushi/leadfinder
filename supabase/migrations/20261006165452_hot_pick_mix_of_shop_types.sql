create or replace function public.worker_pick_hot(p_code text, p_countries text[] default array['IN'], p_limit int default 10)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
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
end $$;

update public.leads set hot_date = null where hot_date = private.today_ist() and call_count = 0;
