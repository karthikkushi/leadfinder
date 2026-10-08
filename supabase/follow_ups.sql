-- Follow-ups and re-ranking (2026-10-08). Applied to the Lead Finder project (eojvxcwvnsowfifxehaa) as migration "follow_ups".
-- Why: in the first 23 calls every "interested" shop already had a weak website, and every shop with no website
-- (or only Instagram) said no. Shops that already paid for a website know they need one, so weak sites now rank
-- level with no-website shops, in every shop type.
-- ponytail: learning is still per shop type only; learn per website status too once there are ~50 more calls.

create or replace function private.score_lead()
 returns trigger language plpgsql security definer set search_path to ''
as $function$
declare pts int := 0; why text[] := '{}'; w int; adj int; share real; is_focus boolean;
begin
  select f.weight into w from public.focus f where f.country = new.country and f.category = new.category;
  is_focus := w is not null;

  -- 1. need (the biggest factor). A weak or broken website ranks with no website: they already pay for one.
  case new.website_status
    when 'none' then pts := 52; why := array_append(why, 'No website');
    when 'social_only' then pts := 48; why := array_append(why, 'No website, only social media');
    when 'directory_only' then pts := 48; why := array_append(why, 'No website, only directory listings');
    when 'dead' then pts := 54; why := array_append(why, 'Their website is not working');
    when 'weak' then pts := 50 + least(8, 2 * coalesce(cardinality(new.issues), 0));
                     why := array_append(why, 'Website needs work: ' || coalesce(lower(new.issues[1]), 'several problems'));
    when 'unknown' then pts := 8;
    else pts := -100;
  end case;
  if new.verified and new.checked_at is not null and new.priority = 1 then
    pts := pts + 5; why := array_append(why, 'Checked: no website of their own online');
  end if;

  -- 2. competitors nearby already have websites
  if coalesce(new.rivals_nearby, 0) >= 3 then
    share := new.rivals_with_site::real / new.rivals_nearby;
    pts := pts + round(20 * share);
    if new.rivals_with_site >= 2 and share >= 0.4 then
      why := array_append(why, format('%s of %s similar shops nearby have websites', new.rivals_with_site, new.rivals_nearby));
    end if;
  end if;

  -- 3. can we reach the owner?
  case new.phone_type
    when 'mobile' then pts := pts + 10; why := array_append(why, 'Mobile number: likely the owner, WhatsApp works');
    when 'fixed_or_mobile' then pts := pts + 5;
    when 'toll_free' then pts := pts - 40; why := array_append(why, 'Toll-free number: probably a big company');
    else null;
  end case;

  -- 4. does the shop really exist / still trade?
  if new.confidence is not null then
    pts := pts + round((new.confidence - 0.5) * 30);
    if new.confidence < 0.35 then pts := pts - 15; why := array_append(why, 'Listing may be out of date'); end if;
  end if;

  -- 5. value of the shop type, and busy area
  if is_focus then pts := pts + w; else pts := pts - 60; end if;
  if coalesce(new.brands_nearby, 0) >= 15 then pts := pts + 8; why := array_append(why, 'Busy commercial area');
  elsif coalesce(new.brands_nearby, 0) >= 5 then pts := pts + 4;
  end if;

  -- 6. already digital, growing
  if new.has_instagram then pts := pts + 5; why := array_append(why, 'Active on Instagram'); end if;
  if new.email is not null then pts := pts + 2; end if;
  if new.branches between 2 and 3 then
    pts := pts + 5; why := array_append(why, format('%s branches: a growing business', new.branches));
  end if;

  -- 7. learned from Shreya's calls
  select cs.adjust into adj from public.category_stats cs where cs.country = new.country and cs.category = new.category;
  if coalesce(adj, 0) <> 0 then
    pts := pts + adj;
    if adj >= 5 then why := array_append(why, 'Shops like this have said yes before'); end if;
  end if;

  new.lead_score := pts;
  new.reasons := why;
  new.tier := case when not is_focus or pts < 0 or new.priority = 3 then 'X'
                   when pts >= 100 then 'A' when pts >= 85 then 'B' else 'C' end;
  return new;
end $function$;

-- Follow-ups: interested, "will ask the owner" and sample sent all come back after 2 days, with a message ready.
create or replace function public.app_update_lead(p_code text, p_id uuid, p_outcome text, p_note text default null, p_callback_at timestamptz default null)
 returns json language plpgsql security definer set search_path to ''
as $function$
declare m public.team := private.require(p_code, array['admin','caller']);
declare l public.leads; new_stage text; follow timestamptz;
begin
  select * into l from public.leads where id = p_id;
  if l.id is null then raise exception 'Lead not found'; end if;
  -- no answer -> try tomorrow, then 3 days later, then set aside; interested / asking the owner / sample sent -> 2 days
  new_stage := case p_outcome
    when 'no_answer' then case when l.call_count + 1 >= 3 then 'skip' else 'callback' end
    -- sending the sample keeps an interested shop interested (the learning counts interested shops as a yes)
    when 'sample_sent' then case when l.stage = 'interested' then 'interested' else 'callback' end
    when 'ask_owner' then 'callback'
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
                 when p_outcome in ('sample_sent', 'ask_owner', 'interested') then coalesce(p_callback_at, now() + interval '2 days')
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

-- "callbacks due" now counts interested shops whose follow-up day has come, too.
create or replace function public.app_summary(p_code text, p_country text default 'IN')
 returns json language plpgsql security definer set search_path to ''
as $function$
declare m public.team := private.require(p_code, array['admin', 'caller']);
declare today date := private.today_ist();
begin
  return json_build_object(
    'today', today,
    'hot_today', (select count(*) from public.leads where country = p_country and hot_date = today),
    'hot_done', (select count(*) from public.leads where country = p_country and hot_date = today and call_count > 0),
    'hot_earlier', (select count(*) from public.leads where country = p_country and hot_date < today and stage = 'new'),
    'callbacks_due', (select count(*) from public.leads where stage in ('callback', 'interested') and country = p_country
                        and callback_at < ((today + 1)::timestamp at time zone 'Asia/Kolkata')),
    'calls_today', (select count(*) from public.call_log
                     where created_at >= (today::timestamp at time zone 'Asia/Kolkata')),
    'won', (select count(*) from public.leads where stage = 'won' and country = p_country),
    'countries', (select coalesce(json_agg(json_build_object('code', country, 'total', data->'total') order by country), '[]'::json)
                    from public.summary_cache),
    'summary', (select data from public.summary_cache where country = p_country),
    'summary_at', (select updated_at from public.summary_cache where country = p_country));
end $function$;

-- Interested shops already called get their first follow-up in 2 days.
update public.leads set callback_at = now() + interval '2 days' where stage = 'interested' and callback_at is null;

-- Stats: "will ask the owner" is an answered call.
-- (app_funnel's answered list gains 'ask_owner'; applied in place with replace() on the function text.)
