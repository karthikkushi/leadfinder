#!/bin/bash
# Double-click: connects Gmail so the agents can send the morning lead email.
cd "$(dirname "$0")"
GUSER="kushikarthikeinmr@gmail.com"   # the account that sends the email
clear
echo "=== Morning email setup ==="
echo
echo "Sending account: $GUSER"
echo "Create an app password at https://myaccount.google.com/apppasswords (name it 'Lead Finder')"
echo "and copy the 16-letter code."
echo
for attempt in 1 2 3; do
  read -r -s -p "Paste the 16-letter code here and press Enter (it stays hidden): " GPASS
  echo
  GPASS=$(printf "%s" "$GPASS" | tr -d ' \t')
  if [[ ! "$GPASS" =~ ^[a-zA-Z]{16}$ ]]; then
    echo "That isn't a 16-letter code. Copy it again from the Google page and paste it."
    echo
    continue
  fi
  echo "Checking with Gmail..."
  if GUSER="$GUSER" GPASS="$GPASS" .venv/bin/python - <<'PY'
import os, smtplib, ssl, sys, certifi
try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(cafile=certifi.where())) as s:
        s.login(os.environ["GUSER"], os.environ["GPASS"])
except smtplib.SMTPAuthenticationError:
    print("Gmail rejected this code. Make sure you're signed in to the right account and create a new code.")
    sys.exit(1)
except Exception as e:
    print(f"Couldn't reach Gmail ({type(e).__name__}). Check the internet connection and try again.")
    sys.exit(1)
PY
  then
    grep -v '^GMAIL_USER=\|^GMAIL_APP_PASSWORD=' .env > .env.tmp && mv .env.tmp .env && chmod 600 .env
    printf 'GMAIL_USER=%s\nGMAIL_APP_PASSWORD=%s\n' "$GUSER" "$GPASS" >> .env
    printf "%s" "$GUSER" | gh secret set GMAIL_USER -R karthikkushi/leadfinder
    printf "%s" "$GPASS" | gh secret set GMAIL_APP_PASSWORD -R karthikkushi/leadfinder
    echo
    echo "Gmail connected. Sending your first email with today's leads..."
    .venv/bin/python -m leadfinder email --since-hours 24 2>&1 | grep -E "Sent|not set up|rror" || true
    echo
    echo "All set. Every morning's email will now be sent automatically."
    read -r -p "Press Enter to close." _
    exit 0
  fi
  echo
done
echo "Setup didn't finish. Double-click 'Set Up Email' to try again."
read -r -p "Press Enter to close." _
