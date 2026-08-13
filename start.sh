#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-${SERVERMAN_PORT:-8501}}"
HOST="${HOST:-127.0.0.1}"

if [[ -x .venv/bin/streamlit ]]; then
  STREAMLIT=".venv/bin/streamlit"
else
  STREAMLIT="streamlit"
fi

exec "$STREAMLIT" run app.py \
  --server.port "$PORT" \
  --server.address "$HOST" \
  --server.headless true
