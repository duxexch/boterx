#!/usr/bin/env bash
# Rebuild the purged Tailwind stylesheet used by the dashboard + webapp home.
# Run from the repo root whenever templates/JS gain new Tailwind classes,
# then bump the ?v= query on the tailwind.build.css <link> in base.html/home.html.
set -euo pipefail
cd "$(dirname "$0")"
npx -y tailwindcss@3.4.5 \
  -c dashboard/tailwind.config.js \
  -i dashboard/tailwind.input.css \
  -o dashboard/static/css/tailwind.build.css \
  --minify
echo "Built dashboard/static/css/tailwind.build.css"
