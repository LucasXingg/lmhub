#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${PORT:-${SERVERMAN_PORT:-8501}}"
HOST="${HOST:-127.0.0.1}"

STREAMLIT_ARGS=(
  run app.py
  --global.developmentMode=false
  --server.port "$PORT"
  --server.address "$HOST"
  --server.headless true
)

if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m streamlit "${STREAMLIT_ARGS[@]}"
fi

# Legacy fallback for older --target installs
if [[ -d .python_packages ]]; then
  export PYTHONPATH="${ROOT}/.python_packages${PYTHONPATH:+:$PYTHONPATH}"
fi

exec python3 -m streamlit "${STREAMLIT_ARGS[@]}"
