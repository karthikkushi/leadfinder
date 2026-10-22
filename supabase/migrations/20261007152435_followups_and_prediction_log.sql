alter table public.call_log add column if not exists tier text, add column if not exists lead_score int;

create or replace function public.app_update_lead(p_code text, p_id uuid, p_outcome text, p_note text default null, p_callback_at timestamptz default null)
returns json language plpgsql security definer set search_path to '' as $function$
declare m public.team := private.require(p_code, array['admin','caller']);
declare l public.leads; new_stage text; follow timestamptz;
begin
  select * into l from public.leads where id = p_id;
  if l.id is null then raise exception 'Lead not found'; end if;
  -- follow-ups: no answer -> try tomorrow, then 3 days later, then set aside; sample sent -> follow up in 2 days
  new_stage := case p_outcome
    when 'no_answer' then case when l.call_count + 1 >= 3 then 'skip' else 'callback' end
    when 'sample_sent' then 'callback'
    when 'callback' then 'callback'
    when 'interested' then 'interested'
    when 'not_interested' then 'not_interested'
    when 'won' then 'won'
    when 'wrong_number' then 'wrong_number'
    when 'do_not_call' then 'do_not_call'
    when 'has_website' then 'skip'
    when 'reopen' then 'new'
    else null end;
  if new_stage is null and p_outcome <> 'note' then raise exception 'Unknown outcome %', p_outcome; end if;
  if p_outcome = 'callback' and p_callback_at is null then raise exception 'Pick a callback time'; end if;
  follow := case when p_outcome = 'callback' then p_callback_at
                 when p_outcome = 'sample_sent' then coalesce(p_callback_at, now() + interval '2 days')
                 when new_stage = 'callback' then now() + case when l.call_count = 0 then interval '1 day' else interval '3 days' end
                 when p_outcome = 'note' then l.callback_at end;

  update public.leads x set
    stage = coalesce(new_stage, x.stage),
    callback_at = follow,
    notes = case when p_note is not null and length(trim(p_note)) > 0 then trim(p_note)
                 when p_outcome = 'no_answer' and new_stage = 'skip' then trim(coalesce(x.notes, '') || ' No answer 3 times.')
                 else x.notes end,
    last_outcome = case when p_outcome in ('note', 'reopen') then x.last_outcome else p_outcome end,
    last_called_at = case when p_outcome in ('note', 'reopen') then x.last_called_at else now() end,
    call_count = x.call_count + case when p_outcome in ('note', 'reopen', 'has_website', 'sample_sent') then 0 else 1 end,
    called_by = case when p_outcome in ('note', 'reopen') then x.called_by else m.id end,
    updated_at = now()
  where x.id = p_id;

  insert into public.call_log (lead_id, member_id, outcome, note, tier, lead_score)
  values (p_id, m.id, p_outcome, nullif(trim(coalesce(p_note, '')), ''), l.tier, l.lead_score);
  return json_build_object('ok', true, 'stage', (select stage from public.leads where id = p_id));
end $function$;
