#!/bin/bash
# Double-click: connects a Gmail account so the agents can send the morning lead email.
cd "$(dirname "$0")"
echo "=== Morning email setup ==="
echo
echo "1. A Google page will open. Sign in with the Gmail account that should SEND the email."
echo "   (If it says app passwords aren't available, turn on 2-Step Verification first.)"
echo "2. Create an app password named 'Lead Finder' and copy the 16-letter code."
echo
read -r -p "Press Enter to open the Google page..." _
open "https://myaccount.google.com/apppasswords"
echo
read -r -p "Gmail address that sends the email [kushikarthikeinmr@gmail.com]: " GUSER
GUSER=${GUSER:-kushikarthikeinmr@gmail.com}
read -r -s -p "Paste the 16-letter app password (hidden): " GPASS
echo
GPASS=$(echo "$GPASS" | tr -d ' ')
echo "Testing the login..."
if ! GUSER="$GUSER" GPASS="$GPASS" .venv/bin/python -c '
import os, smtplib, ssl, certifi
with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(cafile=certifi.where())) as s:
    s.login(os.environ["GUSER"], os.environ["GPASS"])
'; then
  echo "Gmail did not accept that. Check the address and app password, then double-click this file again."
  read -r -p "Press Enter to close." _; exit 1
fi
grep -v '^GMAIL_USER=\|^GMAIL_APP_PASSWORD=' .env > .env.tmp && mv .env.tmp .env && chmod 600 .env
printf 'GMAIL_USER=%s\nGMAIL_APP_PASSWORD=%s\n' "$GUSER" "$GPASS" >> .env
printf "%s" "$GUSER" | gh secret set GMAIL_USER -R karthikkushi/leadfinder
printf "%s" "$GPASS" | gh secret set GMAIL_APP_PASSWORD -R karthikkushi/leadfinder
echo
echo "Done. Sending a test email with today's leads..."
.venv/bin/python -m leadfinder email --since-hours 24
echo
read -r -p "All set. Press Enter to close." _
