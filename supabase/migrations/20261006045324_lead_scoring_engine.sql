alter table public.leads
  add column if not exists confidence real,
  add column if not exists phone_type text,
  add column if not exists rivals_nearby int,
  add column if not exists rivals_with_site int,
  add column if not exists brands_nearby int,
  add column if not exists has_instagram boolean not null default false,
  add column if not exists branches int,
  add column if not exists features_at timestamptz,
  add column if not exists lead_score int not null default 0,
  add column if not exists tier text not null default 'C',
  add column if not exists reasons text[] not null default '{}';

-- Which shop types we sell to, per country, and how valuable each is (points added to the score).
create table if not exists public.focus (
  country text not null,
  category text not null,
  weight int not null default 7,
  primary key (country, category)
);
alter table public.focus enable row level security;
revoke all on public.focus from anon, authenticated;

insert into public.focus (country, category, weight) values
  ('IN','dentist',10),('IN','dermatologist',10),('IN','clinic',9),('IN','physio',8),('IN','eye_clinic',8),('IN','vet',7),
  ('IN','salon_beauty',8),('IN','gym_fitness',8),
  ('IN','jewellery',9),('IN','clothing',7),('IN','furniture_home',9),('IN','pet_shop',7),
  ('IN','events_photo',8),('IN','tuition',7),('IN','restaurant_cafe',6),('IN','bakery_sweets',6),
  ('US','dentist',10),('US','dermatologist',10),('US','clinic',9),('US','physio',8),('US','eye_clinic',8),('US','vet',7),
  ('US','salon_beauty',8),('US','gym_fitness',8),('US','jewellery',9),('US','clothing',7),('US','furniture_home',9),
  ('US','pet_shop',7),('US','events_photo',8),('US','tuition',7),('US','restaurant_cafe',6),('US','bakery_sweets',6),
  ('US','home_services',10)
on conflict do nothing;

-- Learning from calls: how each shop type answers, compared with the average. Refreshed by the daily run.
create table if not exists public.category_stats (
  country text not null,
  category text not null,
  calls int not null default 0,
  positive int not null default 0,
  adjust int not null default 0,
  updated_at timestamptz not null default now(),
  primary key (country, category)
);
alter table public.category_stats enable row level security;
revoke all on public.category_stats from anon, authenticated;

create or replace function private.score_lead()
returns trigger language plpgsql security definer set search_path = '' as $$
declare pts int := 0; why text[] := '{}'; w int; adj int; share real; is_focus boolean;
begin
  select f.weight into w from public.focus f where f.country = new.country and f.category = new.category;
  is_focus := w is not null;

  -- 1. need: how badly they need a website
  case new.website_status
    when 'none' then pts := 40; why := why || 'No website';
    when 'social_only' then pts := 40; why := why || 'No website, only social media';
    when 'directory_only' then pts := 38; why := why || 'No website, only directory listings';
    when 'dead' then pts := 36; why := why || 'Their website is not working';
    when 'weak' then pts := 18 + least(12, 3 * coalesce(cardinality(new.issues), 0));
                     why := why || ('Website needs work: ' || coalesce(lower(new.issues[1]), 'several problems'));
    when 'unknown' then pts := 10;
    else pts := -100;
  end case;
  if new.verified and new.checked_at is not null and new.priority = 1 then
    pts := pts + 5; why := why || 'Checked: no website of their own online';
  end if;

  -- 2. competitors nearby already have websites
  if coalesce(new.rivals_nearby, 0) >= 3 then
    share := new.rivals_with_site::real / new.rivals_nearby;
    pts := pts + round(20 * share);
    if new.rivals_with_site >= 2 and share >= 0.4 then
      why := why || format('%s of %s similar shops nearby have websites', new.rivals_with_site, new.rivals_nearby);
    end if;
  end if;

  -- 3. can we reach the owner?
  case new.phone_type
    when 'mobile' then pts := pts + 10; why := why || 'Mobile number: likely the owner, WhatsApp works';
    when 'fixed_or_mobile' then pts := pts + 5;
    when 'toll_free' then pts := pts - 40; why := why || 'Toll-free number: probably a big company';
    else null;
  end case;

  -- 4. does the shop really exist / still trade?
  if new.confidence is not null then
    pts := pts + round((new.confidence - 0.5) * 30);
    if new.confidence < 0.35 then pts := pts - 15; why := why || 'Listing may be out of date'; end if;
  end if;

  -- 5. value of the shop type, and busy area
  if is_focus then pts := pts + w; else pts := pts - 60; end if;
  if coalesce(new.brands_nearby, 0) >= 15 then pts := pts + 8; why := why || 'Busy commercial area';
  elsif coalesce(new.brands_nearby, 0) >= 5 then pts := pts + 4;
  end if;

  -- 6. already digital, growing
  if new.has_instagram then pts := pts + 5; why := why || 'Active on Instagram'; end if;
  if new.email is not null then pts := pts + 2; end if;
  if new.branches between 2 and 3 then pts := pts + 5; why := why || format('%s branches: a growing business', new.branches); end if;

  -- 7. learned from Shreya's calls
  select cs.adjust into adj from public.category_stats cs where cs.country = new.country and cs.category = new.category;
  if coalesce(adj, 0) <> 0 then
    pts := pts + adj;
    if adj >= 5 then why := why || 'Shops like this have said yes before'; end if;
  end if;

  new.lead_score := pts;
  new.reasons := why;
  new.tier := case when not is_focus or pts < 0 or new.priority = 3 then 'X'
                   when pts >= 85 then 'A' when pts >= 70 then 'B' else 'C' end;
  return new;
end $$;

drop trigger if exists leads_score on public.leads;
create trigger leads_score before insert or update on public.leads
  for each row execute function private.score_lead();

create index if not exists leads_best_idx on public.leads (country, stage, tier, lead_score desc);
