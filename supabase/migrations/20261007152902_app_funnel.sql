-- Sales funnel by shop type and by the tier the lead had when first called (does "Best" really convert better?)
create or replace function public.app_funnel(p_code text, p_country text default 'IN')
returns json language plpgsql security definer set search_path to '' as $function$
declare m public.team := private.require(p_code, array['admin', 'caller']);
begin
  return (with per as (
    select l.category,
           coalesce((array_agg(c.tier order by c.created_at) filter (where c.tier is not null))[1], l.tier) as tier,
           bool_or(c.outcome not in ('note', 'reopen', 'has_website', 'sample_sent')) as called,
           bool_or(c.outcome in ('callback', 'interested', 'not_interested', 'won', 'do_not_call', 'sample_sent')) as answered,
           bool_or(c.outcome in ('interested', 'won', 'sample_sent')) as interested,
           bool_or(c.outcome = 'sample_sent') as sample,
           bool_or(c.outcome = 'won') as won
      from public.call_log c join public.leads l on l.id = c.lead_id
     where l.country = p_country
     group by l.id, l.category, l.tier),
  g as (select category, tier, called, answered, interested, sample, won from per)
  select json_build_object(
    'total', (select json_build_object('called', count(*) filter (where called), 'answered', count(*) filter (where answered),
                     'interested', count(*) filter (where interested), 'samples', count(*) filter (where sample),
                     'won', count(*) filter (where won)) from g),
    'by_type', (select coalesce(json_agg(t order by t.called desc), '[]'::json) from (
                  select category as key, count(*) filter (where called) as called, count(*) filter (where answered) as answered,
                         count(*) filter (where interested) as interested, count(*) filter (where sample) as samples,
                         count(*) filter (where won) as won from g group by category) t),
    'by_tier', (select coalesce(json_agg(t order by t.key), '[]'::json) from (
                  select coalesce(tier, '?') as key, count(*) filter (where called) as called, count(*) filter (where answered) as answered,
                         count(*) filter (where interested) as interested, count(*) filter (where sample) as samples,
                         count(*) filter (where won) as won from g group by tier) t)));
end $function$;
