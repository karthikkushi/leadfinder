#!/bin/bash
# Double-click: opens the calling app logged in as you (admin). Your code stays in .env on this Mac.
cd "$(dirname "$0")"
CODE=$(grep '^ADMIN_CODE=' .env | cut -d= -f2)
open -a "Microsoft Edge" "https://karthikkushi.github.io/leadfinder/#code=$CODE" 2>/dev/null || open "https://karthikkushi.github.io/leadfinder/#code=$CODE"
