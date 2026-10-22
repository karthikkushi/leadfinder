do $$ begin
  execute replace(pg_get_functiondef('public.app_list'::regproc),
    $r$when 'callbacks' then cond := cond || ' and l.stage = ''callback'''; ord := 'l.callback_at asc nulls last';$r$,
    $r$when 'callbacks' then cond := cond || ' and l.stage in (''callback'', ''interested'')'; ord := 'l.callback_at asc nulls last, l.updated_at desc';$r$);
end $$;
-- today's "no answer" calls made before the follow-up rule existed
update public.leads set stage = 'callback', callback_at = now() + interval '1 day'
 where stage = 'new' and last_outcome = 'no_answer' and call_count > 0;
select position('''callback'', ''interested''' in pg_get_functiondef('public.app_list'::regproc)) > 0 as view_ok;
