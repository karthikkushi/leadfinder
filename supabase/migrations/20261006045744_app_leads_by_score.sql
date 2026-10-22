drop function if exists public.app_leads(text, text, text, text, text, int, text, int, int);
create or replace function public.app_leads(
  p_code text, p_view text default 'to_call', p_country text default null, p_city text default null,
  p_category text default null, p_priority int default null, p_search text default null,
  p_limit int default 50, p_offset int default 0, p_all_types boolean default false)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['admin','caller']);
declare result json;
begin
  select coalesce(json_agg(r), '[]'::json) into result from (
    select l.id, l.name, l.category, l.subcategory, l.country, l.city, l.locality, l.address, l.lat, l.lon,
           l.phone, l.phone_intl, l.email, l.website, l.socials, l.website_status, l.issues, l.verified,
           l.priority, l.score, l.lead_score, l.tier, l.reasons, l.stage, l.callback_at, l.notes, l.last_outcome,
           l.last_called_at, l.call_count, (l.checked_at is not null) as checked
      from public.leads l
     where (p_country is null or l.country = p_country)
       and (p_city is null or l.city = p_city)
       and (p_category is null or l.category = p_category)
       and (p_priority is null or l.priority = p_priority)
       and (p_search is null or l.name ilike '%' || p_search || '%' or l.phone_intl like '%' || p_search || '%'
            or l.locality ilike '%' || p_search || '%')
       and case p_view
             when 'to_call' then l.stage = 'new' and l.priority in (1, 2) and l.phone_intl is not null
                                 and (p_all_types or l.tier <> 'X')
             when 'callbacks' then l.stage = 'callback'
             when 'interested' then l.stage = 'interested'
             when 'won' then l.stage = 'won'
             when 'done' then l.stage in ('not_interested', 'wrong_number', 'do_not_call', 'skip')
             else true
           end
     order by
       case when p_view = 'callbacks' then extract(epoch from l.callback_at) end asc nulls last,
       case when p_view in ('interested', 'won', 'done') then extract(epoch from l.updated_at) end desc nulls last,
       (l.last_called_at is not null) asc,
       (l.checked_at is not null) desc,
       l.lead_score desc,
       l.name asc
     limit least(greatest(p_limit, 1), 200) offset greatest(p_offset, 0)
  ) r;
  return result;
end $$;
revoke all on function public.app_leads(text, text, text, text, text, int, text, int, int, boolean) from public;
grant execute on function public.app_leads(text, text, text, text, text, int, text, int, int, boolean) to anon, authenticated;
