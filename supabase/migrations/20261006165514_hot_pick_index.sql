create index if not exists leads_hot_candidates_idx on public.leads (country, category, list_rank desc)
  where stage = 'new' and priority in (1, 2) and phone_intl is not null and tier <> 'X'
    and checked_at is not null and hot_date is null and call_count = 0;
analyze public.leads;
