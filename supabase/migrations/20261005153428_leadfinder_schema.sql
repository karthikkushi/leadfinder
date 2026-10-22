create extension if not exists pgcrypto with schema extensions;
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table public.team (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  role text not null check (role in ('admin','caller','worker')),
  code_hash text not null unique,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.leads (
  id uuid primary key default gen_random_uuid(),
  source_key text not null unique,
  sources text[] not null default '{}',
  name text not null,
  category text not null,
  subcategory text,
  country text not null,
  city text not null,
  locality text,
  address text,
  lat double precision,
  lon double precision,
  phone text,
  phone_intl text,
  email text,
  website text,
  socials text[] not null default '{}',
  website_status text not null default 'unknown'
    check (website_status in ('none','social_only','directory_only','dead','weak','good','unknown')),
  issues text[] not null default '{}',
  verified boolean not null default false,
  priority smallint not null default 1,
  score int not null default 0,
  stage text not null default 'new'
    check (stage in ('new','callback','interested','not_interested','won','wrong_number','do_not_call','skip')),
  callback_at timestamptz,
  notes text,
  last_outcome text,
  last_called_at timestamptz,
  call_count int not null default 0,
  called_by uuid references public.team(id),
  check_claimed_at timestamptz,
  checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index leads_queue_idx on public.leads (stage, priority, score desc);
create index leads_place_idx on public.leads (country, city, category);
create index leads_unchecked_idx on public.leads (priority, score desc) where checked_at is null;
create index leads_phone_idx on public.leads (phone_intl, city);
create index leads_callback_idx on public.leads (callback_at) where stage = 'callback';

create table public.call_log (
  id bigint generated always as identity primary key,
  lead_id uuid not null references public.leads(id) on delete cascade,
  member_id uuid references public.team(id),
  outcome text not null,
  note text,
  created_at timestamptz not null default now()
);
create index call_log_lead_idx on public.call_log (lead_id);
create index call_log_member_idx on public.call_log (member_id, created_at);

create table public.search_jobs (
  id bigint generated always as identity primary key,
  country text not null,
  city text not null,
  category text not null default 'all',
  status text not null default 'queued' check (status in ('queued','running','done','failed')),
  requested_by uuid references public.team(id),
  found int,
  added int,
  message text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);
create index search_jobs_status_idx on public.search_jobs (status, created_at);

alter table public.team enable row level security;
alter table public.leads enable row level security;
alter table public.call_log enable row level security;
alter table public.search_jobs enable row level security;
revoke all on public.team, public.leads, public.call_log, public.search_jobs from anon, authenticated;

-- Access: every app/worker call goes through the functions below, which check a personal access code.
create or replace function private.require(p_code text, p_roles text[])
returns public.team language plpgsql stable security definer set search_path = '' as $$
declare m public.team;
begin
  select t.* into m from public.team t
   where t.active
     and t.code_hash = encode(extensions.digest(coalesce(p_code, ''), 'sha256'), 'hex')
     and t.role = any(p_roles);
  if m.id is null then
    raise exception 'Invalid access code' using errcode = '28000';
  end if;
  return m;
end $$;
revoke all on function private.require(text, text[]) from public, anon, authenticated;
