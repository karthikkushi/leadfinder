create or replace function private.score_lead()
returns trigger language plpgsql security definer set search_path = '' as $$
declare pts int := 0; why text[] := '{}'; w int; adj int; share real; is_focus boolean;
begin
  select f.weight into w from public.focus f where f.country = new.country and f.category = new.category;
  is_focus := w is not null;

  -- 1. need: how badly they need a website
  case new.website_status
    when 'none' then pts := 40; why := array_append(why, 'No website');
    when 'social_only' then pts := 40; why := array_append(why, 'No website, only social media');
    when 'directory_only' then pts := 38; why := array_append(why, 'No website, only directory listings');
    when 'dead' then pts := 36; why := array_append(why, 'Their website is not working');
    when 'weak' then pts := 18 + least(12, 3 * coalesce(cardinality(new.issues), 0));
                     why := array_append(why, 'Website needs work: ' || coalesce(lower(new.issues[1]), 'several problems'));
    when 'unknown' then pts := 10;
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
                   when pts >= 85 then 'A' when pts >= 70 then 'B' else 'C' end;
  return new;
end $$;
