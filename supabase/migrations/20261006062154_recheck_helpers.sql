-- Shops the checker marked "no website": used to audit/re-check them with improved rules.
create or replace function public.worker_no_website_checked(p_code text, p_limit int default 500)
returns json language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
begin
  return (select coalesce(json_agg(x), '[]'::json) from (
    select id, name, category, subcategory, country, city, locality, address, phone, phone_intl, email, website,
           socials, website_status, issues, priority, score
      from public.leads
     where priority = 1 and checked_at is not null and stage in ('new', 'callback')
     order by lead_score desc limit least(greatest(p_limit, 1), 2000)) x);
end $$;

-- Send shops back to the "waiting for a website check" queue.
create or replace function public.worker_reset_checks(p_code text, p_ids uuid[])
returns int language plpgsql security definer set search_path = '' as $$
declare m public.team := private.require(p_code, array['worker']);
declare n int;
begin
  update public.leads set checked_at = null, verified = false, check_claimed_at = null where id = any(p_ids);
  get diagnostics n = row_count;
  return n;
end $$;
revoke all on function public.worker_no_website_checked(text, int) from public;
grant execute on function public.worker_no_website_checked(text, int) to anon, authenticated;
revoke all on function public.worker_reset_checks(text, uuid[]) from public;
grant execute on function public.worker_reset_checks(text, uuid[]) to anon, authenticated;
