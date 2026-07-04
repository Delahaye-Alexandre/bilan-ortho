#!/usr/bin/env bash
# Démarrage silencieux pour le lanceur Windows (BilanOrtho.exe).
# Idempotent : ne démarre Ollama et le serveur que s'ils ne répondent pas déjà
# (évite le « address already in use » d'un double lancement).
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${BILAN_ORTHO_DATA_DIR:-$HOME/.local/share/bilan-ortho}"
mkdir -p "$LOG_DIR"

# Ollama (normalement déjà lancé par systemd dans la distro)
if ! curl -sf -m 2 "${OLLAMA_HOST:-http://localhost:11434}/api/tags" >/dev/null 2>&1; then
  (nohup ollama serve >>"$LOG_DIR/ollama.log" 2>&1 &) || true
fi

# Serveur bilan-ortho
if ! curl -sf -m 2 http://127.0.0.1:8000/api/status >/dev/null 2>&1; then
  cd "$DIR"
  (nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 \
     >>"$LOG_DIR/serveur.log" 2>&1 &)
fi
