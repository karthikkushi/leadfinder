create table if not exists private.web_enquiries (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  phone_intl text not null,
  ip_hash text,
  lead_id uuid
);
create index if not exists web_enquiries_phone_time on private.web_enquiries (phone_intl, created_at desc);
create index if not exists web_enquiries_ip_time on private.web_enquiries (ip_hash, created_at desc);
create index if not exists web_enquiries_time on private.web_enquiries (created_at desc);
alter table private.web_enquiries enable row level security;

create or replace function public.web_enquiry(
  p_name text,
  p_phone text,
  p_shop text default null,
  p_category text default null,
  p_area text default null,
  p_city text default null,
  p_country text default 'IN',
  p_message text default null,
  p_page text default null,
  p_website text default null
)
returns json
language plpgsql
security definer
set search_path to ''
as $$
declare
  v_country text := upper(coalesce(nullif(trim(p_country), ''), 'IN'));
  v_digits text := regexp_replace(coalesce(p_phone, ''), '\D', '', 'g');
  v_phone text;
  v_name text := left(regexp_replace(trim(coalesce(p_name, '')), '\s+', ' ', 'g'), 80);
  v_shop text := nullif(left(regexp_replace(trim(coalesce(p_shop, '')), '\s+', ' ', 'g'), 100), '');
  v_area text := nullif(left(regexp_replace(trim(coalesce(p_area, '')), '\s+', ' ', 'g'), 80), '');
  v_city text := nullif(left(regexp_replace(trim(coalesce(p_city, '')), '\s+', ' ', 'g'), 60), '');
  v_message text := nullif(left(trim(coalesce(p_message, '')), 500), '');
  v_page text := case when p_page ~ '^https?://' then left(p_page, 300) end;
  v_category text := case when p_category in (
    'dentist', 'dermatologist', 'clinic', 'physio', 'eye_clinic', 'vet', 'pet_shop', 'salon_beauty', 'gym_fitness',
    'jewellery', 'clothing', 'furniture_home', 'events_photo', 'tuition', 'restaurant_cafe', 'bakery_sweets',
    'home_services') then p_category else 'general_shop' end;
  v_headers json := nullif(current_setting('request.headers', true), '')::json;
  v_ip text := coalesce(v_headers ->> 'cf-connecting-ip', nullif(trim(split_part(v_headers ->> 'x-forwarded-for', ',', 1)), ''));
  v_ip_hash text := case when v_ip is not null then md5('kalvio-web:' || v_ip) end;
  v_note text;
  v_lead uuid;
begin
  if coalesce(p_website, '') <> '' then
    return json_build_object('ok', true);
  end if;

  if char_length(v_name) < 2 then
    raise exception 'name_required' using errcode = '22023';
  end if;
  if v_country not in ('IN', 'US') then
    v_country := 'IN';
  end if;
  if v_country = 'IN' then
    if length(v_digits) = 11 and left(v_digits, 1) = '0' then v_digits := substr(v_digits, 2); end if;
    if length(v_digits) = 10 then v_digits := '91' || v_digits; end if;
  elsif length(v_digits) = 10 then
    v_digits := '1' || v_digits;
  end if;
  if length(v_digits) not between 11 and 15 then
    raise exception 'phone_invalid' using errcode = '22023';
  end if;
  v_phone := '+' || v_digits;

  if v_ip_hash is not null and (select count(*) from private.web_enquiries
      where ip_hash = v_ip_hash and created_at > now() - interval '1 hour') >= 10 then
    raise exception 'rate_limited' using errcode = '22023';
  end if;
  if (select count(*) from private.web_enquiries where created_at > now() - interval '1 hour') >= 300 then
    raise exception 'rate_limited' using errcode = '22023';
  end if;
  if (select count(*) from private.web_enquiries
      where phone_intl = v_phone and created_at > now() - interval '1 day') >= 3 then
    return json_build_object('ok', true);
  end if;

  v_note := left(concat_ws(' · ',
    to_char(now() at time zone case v_country when 'US' then 'America/Chicago' else 'Asia/Kolkata' end, 'DD Mon YYYY HH24:MI'),
    'Website enquiry from ' || v_name,
    'Shop: ' || v_shop,
    'Area: ' || v_area,
    v_message,
    'Page: ' || v_page), 900);

  select l.id into v_lead from public.leads l
   where l.phone_intl = v_phone
   order by (l.stage = 'won') desc, l.updated_at desc
   limit 1;

  if v_lead is null then
    insert into public.leads (source_key, sources, name, category, country, city, locality, phone, phone_intl, stage, notes, priority)
    values ('web:' || v_digits, array['kalvio_web'], coalesce(v_shop, v_name), v_category, v_country,
            coalesce(v_city, case v_country when 'US' then 'Unknown' else 'Bengaluru' end), v_area, v_phone, v_phone,
            'interested', v_note, 1)
    on conflict (source_key) do update
      set stage = case when public.leads.stage = 'won' then 'won' else 'interested' end,
          notes = left(concat_ws(E'\n', public.leads.notes, excluded.notes), 4000),
          updated_at = now()
    returning id into v_lead;
  else
    update public.leads
       set stage = case when stage = 'won' then stage else 'interested' end,
           sources = case when 'kalvio_web' = any (sources) then sources else sources || array['kalvio_web'] end,
           notes = left(concat_ws(E'\n', notes, v_note), 4000),
           updated_at = now()
     where id = v_lead;
  end if;

  insert into private.web_enquiries (phone_intl, ip_hash, lead_id) values (v_phone, v_ip_hash, v_lead);
  return json_build_object('ok', true);
end
$$;

revoke all on function public.web_enquiry(text, text, text, text, text, text, text, text, text, text) from public;
grant execute on function public.web_enquiry(text, text, text, text, text, text, text, text, text, text) to anon, authenticated;
