#!/usr/bin/env bash
set -euo pipefail

if [ -d "athenaa" ]; then
  cd athenaa
fi

if command -v pip3 >/dev/null 2>&1; then
  pip3 install -r requirements.txt
elif command -v pip >/dev/null 2>&1; then
  pip install -r requirements.txt
fi

exec bash start.sh