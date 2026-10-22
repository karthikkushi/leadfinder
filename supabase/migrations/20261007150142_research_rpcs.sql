-- Leads to research: today's hot leads (or the given ids), with everything the research agent needs.
create or replace function public.worker_research_leads(p_code text, p_ids uuid[] default null, p_countries text[] default array['IN'])
returns json language plpgsql security definer set search_path to '' as $function$
declare m public.team := private.require(p_code, array['worker']);
begin
  return (select coalesce(json_agg(x order by x.lead_score desc), '[]'::json) from (
    select id, name, category, subcategory, country, city, locality, address, lat, lon, phone, phone_intl, email,
           website, socials, website_status, issues, verified, priority, lead_score, tier, reasons, confidence,
           phone_type, rivals_nearby, rivals_with_site, brands_nearby, branches, has_instagram, listing_website
      from public.leads
     where case when p_ids is not null then id = any(p_ids)
                else hot_date = private.today_ist() and country = any(p_countries) end
     limit 50) x);
end $function$;

-- Nearest same-type shops (about 1.3 km) that list a website: candidates for "named rivals".
create or replace function public.worker_rivals(p_code text, p_id uuid, p_limit integer default 15)
returns json language plpgsql security definer set search_path to '' as $function$
declare m public.team := private.require(p_code, array['worker']);
declare l public.leads;
begin
  select * into l from public.leads where id = p_id;
  if l.id is null or l.lat is null then return '[]'::json; end if;
  return (select coalesce(json_agg(r order by r.metres), '[]'::json) from (
    select o.name, o.website, o.website_status, o.locality,
           round(sqrt(power((o.lat - l.lat) * 111000, 2) + power((o.lon - l.lon) * 111000 * cos(radians(l.lat)), 2)))::int as metres
      from public.leads o
     where o.country = l.country and o.city = l.city and o.category = l.category and o.id <> l.id
       and o.website is not null and o.website_status in ('good', 'weak', 'unknown')
       and o.lat between l.lat - 0.012 and l.lat + 0.012 and o.lon between l.lon - 0.012 and l.lon + 0.012
     order by 5 limit least(greatest(p_limit, 1), 40)) r);
end $function$;
