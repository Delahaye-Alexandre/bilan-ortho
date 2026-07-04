#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Active le venv s'il existe
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Vérifie qu'Ollama répond
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
if ! curl -sf "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
  echo "⚠️  Ollama ne répond pas sur ${OLLAMA_HOST}."
  echo "    Lancez-le dans un autre terminal :  ollama serve"
fi

exec uvicorn app.main:app --host 127.0.0.1 --port 8000 "$@"
