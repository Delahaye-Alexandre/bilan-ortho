#!/usr/bin/env bash
# Régénère requirements-lock.txt (verrouillage universel Linux + Windows).
#
#   scripts/verrouiller-dependances.sh                 # garde les versions en place,
#                                                      # résout seulement ce qui manque
#   scripts/verrouiller-dependances.sh --tout-mettre-a-jour   # dernières versions
#
# Nécessite uv (pip install uv, ou uvx). Le fichier produit garde l'en-tête
# explicatif ; vérifier ensuite : pip install -r requirements-lock.txt dans un
# venv neuf, pytest, puis un push sur main pour le build Windows.
set -euo pipefail
cd "$(dirname "$0")/.."
UV="${UV:-uv}"
command -v "$UV" >/dev/null || { echo "uv introuvable : pip install uv" >&2; exit 1; }
tmp="$(mktemp -d)"
trap 'rm -r -- "$tmp"' EXIT
entete="$tmp/entete.txt"; corps="$tmp/corps.txt"; contraintes="$tmp/contraintes.txt"
sed -n '/^#/p;/^[^#]/q' requirements-lock.txt > "$entete"
args=(pip compile requirements.txt --universal --no-header --python-version 3.11 -o "$corps")
if [ "${1:-}" != "--tout-mettre-a-jour" ]; then
  grep -v '^#' requirements-lock.txt | grep '==' > "$contraintes" || true
  args+=(-c "$contraintes")
fi
"$UV" "${args[@]}"
cat "$entete" "$corps" > requirements-lock.txt
echo "requirements-lock.txt régénéré : $(grep -c '^[a-zA-Z]' requirements-lock.txt) paquets"
