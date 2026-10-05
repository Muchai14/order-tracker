#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
if [ ! -x .venv/bin/python ]; then
  echo 'Run uv sync --frozen in this repository first.' >&2
  exit 1
fi
if ! command -v codex >/dev/null 2>&1 && [ -x /Applications/ChatGPT.app/Contents/Resources/codex ]; then
  CODEX_BIN=/Applications/ChatGPT.app/Contents/Resources/codex
  export CODEX_BIN
fi
if [ -z "${CODEX_CA_CERTIFICATE:-}" ] && [ "$(uname -s)" = Darwin ] && [ -r /etc/ssl/cert.pem ]; then
  CODEX_CA_CERTIFICATE=/etc/ssl/cert.pem
  export CODEX_CA_CERTIFICATE
fi
exec .venv/bin/python -m uvicorn server:app --app-dir incident-response --host 127.0.0.1 --port 8001
