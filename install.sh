#!/usr/bin/env bash
# Idempotent dependency install for local + ServerMan hosts.
# Prefers a venv when ensurepip is available; otherwise installs into .python_packages.
set -euo pipefail

cd "$(dirname "$0")"

if python3 -c 'import ensurepip' 2>/dev/null; then
  rm -rf .venv
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
  exit 0
fi

# Minimal Debian/Ubuntu images often lack python3-venv / ensurepip.
rm -rf .venv .python_packages
mkdir -p .python_packages
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt --target .python_packages
