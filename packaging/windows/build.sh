#!/usr/bin/env bash
# Compile BilanOrtho.exe avec le csc.exe intégré à Windows (.NET Framework),
# depuis WSL. Produit : packaging/windows/BilanOrtho.exe (+ copie sur le Bureau
# si RUN de build.sh avec l'argument "bureau").
set -euo pipefail
ICI="$(cd "$(dirname "$0")" && pwd)"
PROJET="$(cd "$ICI/../.." && pwd)"

# 1. Icône (générée si absente) — voir genere_icone.py (partagé avec la CI).
if [ ! -f "$ICI/icone.ico" ]; then
  "$PROJET/.venv/bin/python" "$ICI/genere_icone.py" "$ICI/icone.ico"
fi

# 2. Compilation côté Windows (les sources doivent être sur un lecteur Windows).
WINTMP_W="$(powershell.exe -NoProfile -Command '$env:TEMP' | tr -d '\r')"
WINTMP="$(wslpath "$WINTMP_W")/bilan-ortho-build"
mkdir -p "$WINTMP"
cp "$ICI/BilanOrtho.cs" "$ICI/icone.ico" "$WINTMP/"

CSC='C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
powershell.exe -NoProfile -Command \
  "Set-Location '$WINTMP_W\\bilan-ortho-build'; & '$CSC' /nologo /t:winexe /out:BilanOrtho.exe /win32icon:icone.ico /r:System.Windows.Forms.dll BilanOrtho.cs"

cp "$WINTMP/BilanOrtho.exe" "$ICI/BilanOrtho.exe"
echo "→ $ICI/BilanOrtho.exe"

# 3. Copie sur le Bureau Windows (optionnelle : ./build.sh bureau)
if [ "${1:-}" = "bureau" ]; then
  BUREAU_W="$(powershell.exe -NoProfile -Command "[Environment]::GetFolderPath('Desktop')" | tr -d '\r')"
  cp "$ICI/BilanOrtho.exe" "$(wslpath "$BUREAU_W")/BilanOrtho.exe"
  echo "→ $BUREAU_W\\BilanOrtho.exe"
fi
