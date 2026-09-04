# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commandes

```bash
# Installation (Python 3.11+ ; la CI fait foi avec requirements-lock.txt)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-lock.txt -r requirements-dev.txt

# Lancer l'app (nécessite Ollama : `ollama serve` dans un autre terminal)
./run.sh                          # uvicorn sur 127.0.0.1:8000

# Tests (100 % hors ligne — LLM, embeddings et dictée mockés dans tests/conftest.py)
pytest tests/ -q -rs              # -rs affiche les skips (ex. OCR sans tesseract)
pytest tests/test_api.py -q       # un seul fichier
pytest -k "nom_du_test" -q        # un seul test

# Tests UI (seule couverture du frontend — happy-dom via Bun)
bun tests/ui/test_questions_ui.mjs
bun tests/ui/test_robustesse_ui.mjs

# Lint (config dans pyproject.toml — les ignores y sont commentés, les respecter)
ruff check .
```

**Release** : bumper `__version__` dans `app/__init__.py` **et** créer le tag git `v<version>` — la CI refuse le build Windows si les deux divergent.

## Architecture

Monolithe local-first : un serveur FastAPI (`app/main.py`, ~48 routes) sert un frontend single-page **sans framework ni build** (`app/static/index.html`, JS vanilla). Bind exclusif sur 127.0.0.1 ; aucune donnée ne quitte la machine — c'est l'argument central du produit, pas une préférence technique.

- **Coffre chiffré** : toutes les données patient/bilan vivent dans une base SQLCipher (AES-256) **hors du dépôt** (`~/.local/share/bilan-ortho` ou `BILAN_ORTHO_DATA_DIR`). `security.py` est le portier : l'app est verrouillée tant que la passphrase n'est pas fournie, et les fonctions métier prennent une connexion chiffrée `con` en paramètre plutôt que d'ouvrir la leur.
- **Chaîne IA 100 % locale** : `stt.py` (faster-whisper, l'audio est supprimé après transcription) → `prompts.py`/`llm.py` (Ollama) structure la dictée dans la trame réglementaire (arrêté du 25/07/2023) → `rag.py` réinjecte le style de l'orthophoniste (embeddings + sqlite-vec, stockés dans la même base chiffrée) → `bilan.py` persiste → `export.py` (pdf/docx/md/txt).
- **Tout est config, rien en dur** : cotation NGAP (`cotation.py`), catalogues de tests (`catalogues.py`), trame des bilans et prompts sont éditables depuis l'écran Paramètres. Avant de coder une valeur clinique ou tarifaire, chercher où elle vit dans la config (`config.py`, deux niveaux : défauts + surcharge utilisateur).
- **Points d'entrée** : `run.sh` (dev), `lanceur.py` (exe Windows PyInstaller, single-instance), `scripts/start-serveur.sh` (démarrage silencieux idempotent), `packaging/windows/build.sh`.

## Règles du projet

- **Tout en français** : code, commentaires, docstrings, UI, docs, messages de commit.
- **Vocabulaire neutre** : jamais de formulations genrées dans l'UI et les docs (pas de « testeuse » ; écrire p. ex. « la personne qui teste », « l'orthophoniste »).
- **Cadre médico-légal** : l'app est une *aide à la rédaction*, jamais un outil de diagnostic. Ne pas introduire de formulation qui suggère que l'IA diagnostique, cote ou décide — l'orthophoniste relit, valide et signe (voir `docs/notice-medico-legale.md`).
- **Local only** : ne jamais introduire d'appel réseau externe dans le flux de données patient, ni proposer de modèle Ollama `:cloud`. Les tests doivent rester exécutables hors ligne (mocker via les fixtures de `tests/conftest.py`).
- `docs/business-plan.md` et `docs/audit-2026-07-17.md` sont volontairement hors git (voir `.gitignore`) — ne pas les commiter.
- **Workflow** : travailler en autonomie (plus de validation préalable de plan exigée depuis le 2026-09-04) ; un commit par lot, vérifié isolément. Définition de « fini » : `pytest` + `ruff check .` + tests UI passent.
