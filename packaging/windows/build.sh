#!/usr/bin/env bash
# Compile BilanOrtho.exe avec le csc.exe intégré à Windows (.NET Framework),
# depuis WSL. Produit : packaging/windows/BilanOrtho.exe (+ copie sur le Bureau
# si RUN de build.sh avec l'argument "bureau").
set -euo pipefail
ICI="$(cd "$(dirname "$0")" && pwd)"
PROJET="$(cd "$ICI/../.." && pwd)"

# 1. Icône (générée si absente) — vert de l'app, page blanche stylisée.
if [ ! -f "$ICI/icone.ico" ]; then
  "$PROJET/.venv/bin/python" - "$ICI/icone.ico" <<'EOF'
import sys
from PIL import Image, ImageDraw

def dessine(taille):
    img = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = max(2, taille // 6)
    d.rounded_rectangle([0, 0, taille - 1, taille - 1], radius=r, fill=(47, 111, 78, 255))
    # page blanche
    m = taille // 5
    d.rounded_rectangle([m, int(m * 0.8), taille - m, taille - int(m * 0.8)],
                        radius=max(1, taille // 20), fill=(255, 255, 255, 255))
    # lignes de texte
    lg, ld = m + taille // 12, taille - m - taille // 12
    y0, pas = int(taille * 0.34), max(2, int(taille * 0.12))
    ep = max(1, taille // 24)
    for i in range(3):
        y = y0 + i * pas
        d.rounded_rectangle([lg, y, ld - (taille // 8 if i == 2 else 0), y + ep],
                            radius=ep // 2, fill=(47, 111, 78, 255))
    return img

img = dessine(256)
img.save(sys.argv[1], sizes=[(256, 256), (48, 48), (32, 32), (16, 16)])
EOF
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
