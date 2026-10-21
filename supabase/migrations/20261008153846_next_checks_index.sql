create index if not exists leads_next_check_idx on public.leads (country, priority, lead_score desc)
  where checked_at is null and stage = 'new' and priority in (1, 2) and tier <> 'X';
