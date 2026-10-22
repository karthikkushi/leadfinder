alter table public.leads add column if not exists learn_adj int not null default 0;
create index if not exists leads_city_id_idx on public.leads (country, city, id);

-- remember which learning adjustment a lead was scored with, so re-scoring can be done in small batches
create or replace function private.score_lead_learn()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  select coalesce(cs.adjust, 0) into new.learn_adj from public.category_stats cs
   where cs.country = new.country and cs.category = new.category;
  new.learn_adj := coalesce(new.learn_adj, 0);
  return new;
end $$;
drop trigger if exists leads_learn on public.leads;
create trigger leads_learn before insert or update on public.leads
  for each row execute function private.score_lead_learn();

create or replace function public.worker_refresh_learning(p_code text)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare base real; changed int := 0;
begin
  create temp table s on commit drop as
    select l.country, l.category,
           count(*) filter (where l.last_outcome in ('interested', 'won', 'not_interested', 'has_website')) as calls,
           count(*) filter (where l.stage in ('interested', 'won')) as positive
      from public.leads l where l.call_count > 0 group by 1, 2;
  select coalesce(sum(positive)::real / nullif(sum(calls), 0), 0.1) into base from s;
  base := greatest(base, 0.05);
  insert into public.category_stats as cs (country, category, calls, positive, adjust, updated_at)
  select country, category, calls, positive,
         case when calls < 5 then 0
              else greatest(-10, least(10, round(((positive + 10 * base) / (calls + 10) - base) / base * 10)))::int end,
         now()
    from s
  on conflict (country, category) do update set calls = excluded.calls, positive = excluded.positive,
    adjust = excluded.adjust, updated_at = now();
  get diagnostics changed = row_count;
  return json_build_object('categories', changed, 'base_rate', base);
end $$;

-- re-score up to p_limit open leads whose learning adjustment is out of date; call until it returns 0
create or replace function public.worker_rescore_some(p_code text, p_limit int default 1500)
returns int language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare n int;
begin
  update public.leads l set updated_at = now()
   where l.id in (
     select l2.id from public.leads l2
       join public.category_stats cs on cs.country = l2.country and cs.category = l2.category
      where l2.stage in ('new', 'callback') and l2.learn_adj <> cs.adjust
      limit least(greatest(p_limit, 1), 3000));
  get diagnostics n = row_count;
  return n;
end $$;
revoke all on function public.worker_rescore_some(text, int) from public;
grant execute on function public.worker_rescore_some(text, int) to anon, authenticated;
