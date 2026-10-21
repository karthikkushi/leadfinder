alter table public.leads add column if not exists listing_status text, add column if not exists listing_website text;

create or replace function public.worker_upsert_leads(p_code text, p_rows jsonb)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare n_ins int; n_upd int;
begin
  with src as (
    select * from jsonb_to_recordset(p_rows) as r(
      source_key text, sources text[], name text, category text, subcategory text, country text, city text,
      locality text, address text, lat double precision, lon double precision, phone text, phone_intl text,
      email text, website text, socials text[], website_status text, issues text[], priority smallint, score int)
  ), fresh as (
    select s.* from src s
     where s.phone_intl is null or not exists (
       select 1 from public.leads l where l.phone_intl = s.phone_intl and l.city = s.city and l.source_key <> s.source_key)
  ), up as (
    insert into public.leads as l (source_key, sources, name, category, subcategory, country, city, locality, address,
                                   lat, lon, phone, phone_intl, email, website, socials, website_status, issues,
                                   priority, score, listing_status, listing_website)
    select source_key, coalesce(sources, '{}'), name, category, subcategory, country, city, locality, address,
           lat, lon, phone, phone_intl, email, website, coalesce(socials, '{}'), coalesce(website_status, 'unknown'),
           coalesce(issues, '{}'), coalesce(priority, 1), coalesce(score, 0), website_status, website
      from fresh
    on conflict (source_key) do update set
      sources = excluded.sources, name = excluded.name, subcategory = excluded.subcategory,
      locality = coalesce(excluded.locality, l.locality), address = coalesce(excluded.address, l.address),
      phone = coalesce(l.phone, excluded.phone), phone_intl = coalesce(l.phone_intl, excluded.phone_intl),
      email = coalesce(l.email, excluded.email),
      socials = (select array(select distinct unnest(l.socials || excluded.socials))),
      updated_at = now(),
      -- leads nobody has called yet are re-graded when their listing changed
      category = case when l.stage = 'new' and l.call_count = 0 then excluded.category else l.category end,
      listing_status = excluded.listing_status, listing_website = excluded.listing_website,
      website = case when l.stage = 'new' and l.call_count = 0
                      and (l.listing_status is distinct from excluded.listing_status
                           or l.listing_website is distinct from excluded.listing_website)
                     then excluded.website else l.website end,
      website_status = case when l.stage = 'new' and l.call_count = 0
                      and (l.listing_status is distinct from excluded.listing_status
                           or l.listing_website is distinct from excluded.listing_website)
                     then excluded.website_status else l.website_status end,
      issues = case when l.stage = 'new' and l.call_count = 0
                      and (l.listing_status is distinct from excluded.listing_status
                           or l.listing_website is distinct from excluded.listing_website)
                     then '{}' else l.issues end,
      priority = case when l.stage = 'new' and l.call_count = 0
                      and (l.listing_status is distinct from excluded.listing_status
                           or l.listing_website is distinct from excluded.listing_website)
                     then excluded.priority else l.priority end,
      score = case when l.stage = 'new' and l.call_count = 0
                      and (l.listing_status is distinct from excluded.listing_status
                           or l.listing_website is distinct from excluded.listing_website)
                     then excluded.score else l.score end,
      verified = case when l.stage = 'new' and l.call_count = 0
                      and (l.listing_status is distinct from excluded.listing_status
                           or l.listing_website is distinct from excluded.listing_website)
                     then false else l.verified end,
      checked_at = case when l.stage = 'new' and l.call_count = 0
                      and (l.listing_status is distinct from excluded.listing_status
                           or l.listing_website is distinct from excluded.listing_website)
                     then null else l.checked_at end
    returning (xmax = 0) as inserted
  )
  select count(*) filter (where inserted), count(*) filter (where not inserted) into n_ins, n_upd from up;
  return json_build_object('inserted', n_ins, 'updated', n_upd);
end $$;
revoke all on function public.worker_upsert_leads(text, jsonb) from public;
grant execute on function public.worker_upsert_leads(text, jsonb) to anon, authenticated;
