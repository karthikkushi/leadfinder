alter table public.leads add column if not exists brief jsonb, add column if not exists research jsonb, add column if not exists brief_at timestamptz;

-- the app gets the brief with each lead (only today's hot leads have one)
do $$ begin
  execute replace(pg_get_functiondef('public.app_list'::regproc),
                  '(l.checked_at is not null) as checked', '(l.checked_at is not null) as checked, l.brief');
  execute replace(pg_get_functiondef('public.worker_research_leads'::regproc),
                  'else hot_date = private.today_ist() and country = any(p_countries) end',
                  'else hot_date = private.today_ist() and country = any(p_countries) and brief is null and stage = ''new'' end');
end $$;

create or replace function public.worker_save_brief(p_code text, p_id uuid, p_brief jsonb, p_research jsonb)
returns json language plpgsql security definer set search_path to '' as $function$
declare m public.team := private.require(p_code, array['worker']);
declare c text;
begin
  update public.leads set brief = p_brief, research = p_research, brief_at = now() where id = p_id returning country into c;
  if p_brief->>'call' = 'no' then  -- e.g. a chain outlet: drop it from today's list and pick a replacement
    update public.leads set stage = 'skip', hot_date = null,
           notes = trim(coalesce(notes, '') || ' Skipped by research: ' || coalesce(p_brief->>'headline', ''))
     where id = p_id and stage = 'new';
    return private.pick_hot(array[c], 10);
  end if;
  return json_build_object('saved', true);
end $function$;
