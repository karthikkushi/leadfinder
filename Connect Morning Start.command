#!/bin/bash
# Lets the database's own 7:45 AM timer start the Lead Finder morning run on GitHub
# (GitHub's scheduler runs hours late). The key goes straight into the database's encrypted vault.
cd "$(dirname "$0")" || exit 1
set -a; source .env; set +a

clear
echo "Lead Finder - connect the 7:45 AM morning start"
echo "================================================"
echo
echo "GitHub is opening in your browser with the key already filled in."
echo "On that page:"
echo "  1. Repository access: choose 'Only select repositories' and pick  leadfinder"
echo "  2. Check that Permissions shows  Actions: Read and write"
echo "  3. Click 'Generate token', then copy the key (starts with github_pat_)"
echo
open "https://github.com/settings/personal-access-tokens/new?name=Lead%20Finder%20morning%20start&description=Lets%20the%20Lead%20Finder%20database%20start%20the%20morning%20run&expires_in=366&actions=write"

read -r -s -p "Paste the key here (it stays hidden), then press Enter: " TOKEN
echo
TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"

code=$(printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" | curl -s -o /dev/null -w '%{http_code}' -K - \
  https://api.github.com/repos/karthikkushi/leadfinder/actions/workflows/morning.yml)
if [ "$code" != "200" ]; then
  echo "GitHub didn't accept that key (code $code). Make sure you picked the leadfinder repository, then run this again."
  read -r -p "Press Enter to close" _; exit 1
fi

res=$(printf '{"p_code":"%s","p_token":"%s"}' "$ADMIN_CODE" "$TOKEN" | curl -s --data @- \
  -H "apikey: $SUPABASE_KEY" -H "Content-Type: application/json" "$SUPABASE_URL/rest/v1/rpc/admin_set_github_token")
unset TOKEN
if printf '%s' "$res" | grep -q '"saved"'; then
  echo "Connected. From tomorrow the morning run starts at 7:45 AM."
else
  echo "Saving failed: $res"
fi
read -r -p "Press Enter to close" _
