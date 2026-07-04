"""Génère l'icône de l'application (page blanche sur fond vert de l'app).

Usage : python genere_icone.py <sortie.ico>
Utilisé par build.sh (lanceur WSL) et par la CI (build PyInstaller).
"""
import sys

from PIL import Image, ImageDraw


def dessine(taille: int) -> Image.Image:
    img = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = max(2, taille // 6)
    d.rounded_rectangle([0, 0, taille - 1, taille - 1], radius=r, fill=(47, 111, 78, 255))
    m = taille // 5
    d.rounded_rectangle(
        [m, int(m * 0.8), taille - m, taille - int(m * 0.8)],
        radius=max(1, taille // 20), fill=(255, 255, 255, 255),
    )
    lg, ld = m + taille // 12, taille - m - taille // 12
    y0, pas = int(taille * 0.34), max(2, int(taille * 0.12))
    ep = max(1, taille // 24)
    for i in range(3):
        y = y0 + i * pas
        d.rounded_rectangle(
            [lg, y, ld - (taille // 8 if i == 2 else 0), y + ep],
            radius=ep // 2, fill=(47, 111, 78, 255),
        )
    return img


if __name__ == "__main__":
    dessine(256).save(sys.argv[1], sizes=[(256, 256), (48, 48), (32, 32), (16, 16)])
