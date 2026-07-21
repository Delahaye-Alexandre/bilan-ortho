"""Sauvegarde du coffre : copie cohérente et TOUJOURS chiffrée de la base.

``VACUUM INTO`` produit une copie compacte et transactionnellement cohérente ;
avec SQLCipher, la copie est chiffrée avec la même clé que la base source — la
passphrase reste donc indispensable pour ouvrir une sauvegarde. La restauration
se fait depuis l'écran Paramètres (:func:`app.security.restaurer`) : la copie
est vérifiée avec la passphrase, la base actuelle est sauvegardée en filet,
puis le fichier est remplacé atomiquement.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from . import config

PREFIXE = "bilan-ortho-sauvegarde-"
_META_KEY = "derniere_sauvegarde"


def dossier(cfg: dict) -> Path:
    """Dossier de sauvegarde (créé au besoin). Vide = <données>/sauvegardes."""
    d = ((cfg.get("sauvegarde") or {}).get("dossier") or "").strip()
    p = Path(d).expanduser() if d else config.data_dir() / "sauvegardes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _rotation(d: Path, retention: int) -> None:
    if retention <= 0:
        return
    fichiers = sorted(d.glob(PREFIXE + "*.db"))
    for f in fichiers[:-retention]:
        try:
            f.unlink()
        except OSError:
            pass


def creer(con, cfg: dict) -> dict:
    """Sauvegarde immédiate. Retourne {fichier, octets}."""
    d = dossier(cfg)
    base = PREFIXE + datetime.now().strftime("%Y%m%d-%H%M%S")
    cible, n = d / f"{base}.db", 1
    while cible.exists():  # collision improbable (même seconde)
        n += 1
        cible = d / f"{base}-{n}.db"
    con.commit()  # VACUUM refuse de tourner dans une transaction ouverte
    # Écriture atomique : VACUUM INTO vers un .tmp puis os.replace — un échec
    # en cours de route (disque plein, coupure) ne laisse jamais une sauvegarde
    # partielle qui passerait pour valide. Les .tmp sont invisibles de liste()
    # et de la rotation (motif « *.db »).
    tmp = cible.parent / (cible.name + ".tmp")
    try:
        tmp.unlink(missing_ok=True)  # .tmp orphelin (arrêt brutal) : VACUUM refuse d'écraser
        con.execute("VACUUM INTO ?", (str(tmp),))
        os.replace(tmp, cible)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    con.execute(
        "INSERT INTO meta(key, value) VALUES(?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_META_KEY,),
    )
    retention = int((cfg.get("sauvegarde") or {}).get("retention") or 0)
    _rotation(d, retention)
    return {"fichier": str(cible), "octets": cible.stat().st_size}


def resoudre(nom: str, cfg: dict) -> Path:
    """Chemin d'une sauvegarde existante à partir de son seul NOM de fichier.

    Refuse tout ce qui n'est pas un nom simple de sauvegarde (anti-traversée
    de répertoires : la restauration ne doit jamais lire ailleurs que dans le
    dossier de sauvegarde). Le suffixe ``.db`` exigé écarte de fait les
    ``.tmp`` partiels et les noms du type ``..``.
    """
    separateurs = {"/", "\\", os.sep, os.altsep or "/"}
    if (
        any(s in nom for s in separateurs)
        or not nom.startswith(PREFIXE)
        or not nom.endswith(".db")
    ):
        raise ValueError("Nom de sauvegarde invalide.")
    chemin = dossier(cfg) / nom
    if not chemin.is_file():
        raise ValueError(
            "Cette sauvegarde est introuvable. Fermez puis rouvrez les "
            "Paramètres pour actualiser la liste."
        )
    return chemin


def liste(con, cfg: dict) -> dict:
    """Sauvegardes présentes (récentes d'abord) + horodatage de la dernière."""
    d = dossier(cfg)
    fichiers = [
        {"fichier": f.name, "octets": f.stat().st_size}
        for f in sorted(d.glob(PREFIXE + "*.db"), reverse=True)
    ]
    row = con.execute("SELECT value FROM meta WHERE key=?", (_META_KEY,)).fetchone()
    return {"dossier": str(d), "derniere": row[0] if row else None, "fichiers": fichiers}


def auto_si_due(con, cfg: dict) -> dict | None:
    """Sauvegarde automatique si la dernière date de plus de ``auto_jours``
    jours (0 = désactivée). Retourne le résultat ou None si rien à faire."""
    try:
        jours = int((cfg.get("sauvegarde") or {}).get("auto_jours") or 0)
    except (TypeError, ValueError):
        return None
    if jours <= 0:
        return None
    recente = con.execute(
        "SELECT 1 FROM meta WHERE key=? AND value >= datetime('now', ?)",
        (_META_KEY, f"-{jours} days"),
    ).fetchone()
    if recente:
        return None
    return creer(con, cfg)
