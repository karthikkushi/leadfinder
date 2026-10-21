create extension if not exists pg_net;

-- Admin stores the GitHub key (fine-grained, Actions: write on leadfinder only) in the encrypted vault.
create or replace function public.admin_set_github_token(p_code text, p_token text)
returns json language plpgsql security definer set search_path to '' as $function$
declare m public.team := private.require(p_code, array['admin']);
declare sid uuid;
begin
  if p_token !~ '^github_pat_[A-Za-z0-9_]{40,}$' then raise exception 'That does not look like a fine-grained GitHub key'; end if;
  select id into sid from vault.secrets where name = 'github_dispatch_token';
  if sid is null then
    perform vault.create_secret(p_token, 'github_dispatch_token', 'Starts the Lead Finder morning run');
  else
    perform vault.update_secret(sid, p_token);
  end if;
  return json_build_object('saved', true);
end $function$;

-- Starts the GitHub morning run (GitHub's own scheduler runs hours late on the free plan).
create or replace function private.trigger_morning() returns bigint
language plpgsql security definer set search_path to '' as $function$
declare tok text;
begin
  select decrypted_secret into tok from vault.decrypted_secrets where name = 'github_dispatch_token';
  if tok is null then return null; end if;
  return net.http_post(
    url := 'https://api.github.com/repos/karthikkushi/leadfinder/actions/workflows/morning.yml/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
                                  'User-Agent', 'leadfinder-db', 'X-GitHub-Api-Version', '2022-11-28',
                                  'Content-Type', 'application/json'),
    body := '{"ref": "main", "inputs": {"daily": "yes"}}'::jsonb);
end $function$;
revoke all on function private.trigger_morning() from public, anon, authenticated;

-- 02:15 UTC = 07:45 India time
select cron.schedule('leadfinder-morning', '15 2 * * *', $$select private.trigger_morning()$$);
