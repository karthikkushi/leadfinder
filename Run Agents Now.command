#!/bin/bash
# Double-click: starts the agents in the cloud right now (same as the 6 AM run). Your laptop can be closed after.
cd "$(dirname "$0")"
read -r -p "How many minutes should the agents work? [170]: " MIN
MIN=${MIN:-170}
gh workflow run morning.yml -R karthikkushi/leadfinder -f minutes="$MIN" && echo "Started. The email arrives when they finish."
sleep 4
open "https://github.com/karthikkushi/leadfinder/actions/workflows/morning.yml"
read -r -p "Press Enter to close." _
