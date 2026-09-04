#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${PORT:-${SERVERMAN_PORT:-8501}}"
HOST="${HOST:-127.0.0.1}"
# Streamlit 默认 200MB；视频上传超限时前端会报 Axios 413
MAX_UPLOAD_MB="${STREAMLIT_SERVER_MAX_UPLOAD_SIZE:-1024}"
MAX_MESSAGE_MB="${STREAMLIT_SERVER_MAX_MESSAGE_SIZE:-1024}"

STREAMLIT_ARGS=(
  run app.py
  --global.developmentMode=false
  --server.port "$PORT"
  --server.address "$HOST"
  --server.headless true
  --server.maxUploadSize "$MAX_UPLOAD_MB"
  --server.maxMessageSize "$MAX_MESSAGE_MB"
)

if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m streamlit "${STREAMLIT_ARGS[@]}"
fi

# Legacy fallback for older --target installs
if [[ -d .python_packages ]]; then
  export PYTHONPATH="${ROOT}/.python_packages${PYTHONPATH:+:$PYTHONPATH}"
fi

exec python3 -m streamlit "${STREAMLIT_ARGS[@]}"
