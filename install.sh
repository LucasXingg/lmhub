#!/usr/bin/env bash
# Idempotent dependency install for local + ServerMan hosts.
# Always prefers a real venv so Streamlit is not treated as developmentMode.
set -euo pipefail

cd "$(dirname "$0")"
rm -rf .venv .python_packages

bootstrap_pip() {
  local get_pip
  get_pip="$(mktemp)"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$get_pip"
  .venv/bin/python "$get_pip"
  rm -f "$get_pip"
}

if python3 -c 'import ensurepip' 2>/dev/null; then
  python3 -m venv .venv
else
  # Minimal Debian/Ubuntu: python3-venv/ensurepip missing.
  python3 -m venv --without-pip .venv
  bootstrap_pip
fi

.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
