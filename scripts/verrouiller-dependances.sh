#!/usr/bin/env bash
# Régénère requirements-lock.txt (verrouillage universel Linux + Windows).
#
#   scripts/verrouiller-dependances.sh                        # garde les versions en place,
#                                                             # résout seulement ce qui manque
#   scripts/verrouiller-dependances.sh --monter pillow pypdf  # monte ces paquets, garde le reste
#   scripts/verrouiller-dependances.sh --tout-mettre-a-jour   # dernières versions admises
#
# Deux garde-fous encadrent les montées :
# - un délai de carence (CARENCE_JOURS, 7 par défaut) : une version publiée
#   depuis moins longtemps n'est pas retenue. Un paquet piégé est en général
#   retiré de PyPI en quelques jours, et l'application traite des données de
#   santé : elle n'a aucune raison d'essuyer les plâtres. Pour un correctif de
#   sécurité urgent : CARENCE_JOURS=0 scripts/verrouiller-dependances.sh --monter <paquet>
#   (même réglage si le script refuse une version déjà verrouillée parce
#   qu'elle est plus récente que le délai) ;
# - les plafonds de scripts/plafonds-dependances.txt : montées majeures
#   retenues exprès, chacune avec sa date et ce qui la lèvera.
#
# Nécessite uv (pip install uv, ou uvx). Le fichier produit garde l'en-tête
# explicatif ; vérifier ensuite : pip install -r requirements-lock.txt dans un
# venv neuf, pytest, puis un push sur main pour le build Windows.
set -euo pipefail
cd "$(dirname "$0")/.."
UV="${UV:-uv}"
command -v "$UV" >/dev/null || { echo "uv introuvable : pip install uv" >&2; exit 1; }

mode="garder"
a_monter=()
case "${1:-}" in
  "") ;;
  --tout-mettre-a-jour) mode="tout" ;;
  --monter)
    shift
    a_monter=("$@")
    [ "${#a_monter[@]}" -gt 0 ] || { echo "--monter attend au moins un nom de paquet" >&2; exit 2; }
    mode="monter"
    ;;
  *) echo "Option inconnue : $1 (voir l'en-tête du script)" >&2; exit 2 ;;
esac

tmp="$(mktemp -d)"
trap 'rm -r -- "$tmp"' EXIT
entete="$tmp/entete.txt"; corps="$tmp/corps.txt"; contraintes="$tmp/contraintes.txt"
sed -n '/^#/p;/^[^#]/q' requirements-lock.txt > "$entete"
args=(pip compile requirements.txt --universal --no-header --python-version 3.11
      -o "$corps" -c scripts/plafonds-dependances.txt)
if [ "$mode" != "tout" ]; then
  grep -v '^#' requirements-lock.txt | grep '==' > "$contraintes" || true
  for paquet in "${a_monter[@]}"; do
    # Même normalisation que PyPI (et que uv dans le verrou) : minuscules, tirets.
    nom="$(printf '%s' "$paquet" | tr 'A-Z_.' 'a-z--')"
    [[ "$nom" =~ ^[a-z0-9-]+$ ]] || { echo "Nom de paquet invalide : $paquet" >&2; exit 2; }
    grep -q "^$nom==" "$contraintes" || { echo "Paquet absent du verrou : $paquet" >&2; exit 2; }
    sed -i "/^$nom==/d" "$contraintes"
  done
  args+=(-c "$contraintes")
fi
if [ "$mode" != "garder" ]; then
  args+=(--exclude-newer "$(date -u -d "${CARENCE_JOURS:-7} days ago" +%Y-%m-%dT%H:%M:%SZ)")
fi
"$UV" "${args[@]}"
cat "$entete" "$corps" > requirements-lock.txt
echo "requirements-lock.txt régénéré : $(grep -c '^[a-zA-Z]' requirements-lock.txt) paquets"
