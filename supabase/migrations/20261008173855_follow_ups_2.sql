do $do$
declare d text;
begin
  d := pg_get_functiondef('public.app_update_lead(text,uuid,text,text,timestamptz)'::regprocedure);
  d := replace(d, E'    -- sample_sent is not a call: the result of the last call stays visible\n', '');
  d := replace(d, $x$when p_outcome in ('note', 'reopen', 'sample_sent') then x.$x$, $x$when p_outcome in ('note', 'reopen') then x.$x$);
  execute d;
  d := pg_get_functiondef('public.app_funnel(text,text)'::regprocedure);
  d := replace(d, $x$'do_not_call', 'sample_sent')) as answered$x$, $x$'do_not_call', 'sample_sent', 'ask_owner')) as answered$x$);
  execute d;
end $do$;
