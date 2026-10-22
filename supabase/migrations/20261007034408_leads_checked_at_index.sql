create index if not exists leads_checked_idx on public.leads (country, checked_at desc) where checked_at is not null;
