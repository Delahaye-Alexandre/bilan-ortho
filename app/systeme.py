"""État du système pour le premier lancement guidé : RAM disponible,
présence d'Ollama et des modèles, proposition de modèle adaptée à la machine.

Aucune donnée patient ici : ces fonctions s'exécutent avant même la création
du coffre.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import httpx

# Défauts distribués (recherche juillet 2026, benchmark FR CARTE ; licences
# Apache 2.0). La proposition suit la RAM totale de la machine.
MODELE_16GO = "qwen3.5:9b"      # ~5,5 Go q4 — qualité FR maximale du format
MODELE_8GO = "qwen3.5:4b"       # ~2,4 Go q4 — pour les machines modestes
RAM_MINIMALE_GIO = 7.0          # en dessous : app déconseillée
# Tailles approximatives des téléchargements, pour prévenir AVANT qu'un
# « no space left on device » brut n'arrive à la 40e minute.
TAILLES_GO = {MODELE_16GO: 5.5, MODELE_8GO: 2.4, "nomic-embed-text": 0.3, "bge-m3": 1.2}


def taille_estimee_go(nom: str) -> float:
    """Taille connue d'un modèle distribué, sinon une estimation prudente."""
    base = (nom or "").split(":")[0]
    for cle, go in TAILLES_GO.items():
        if nom == cle or cle.split(":")[0] == base:
            return go
    return 4.0


def disque_libre_gio() -> float:
    """Espace libre du volume qui porte le dossier personnel (là où Ollama
    range ses modèles par défaut), en Gio ; 0 si indéterminable."""
    try:
        return round(shutil.disk_usage(str(Path.home())).free / 1024**3, 1)
    except OSError:
        return 0.0

_NOM_MODELE_RE = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")

# Ollama sait aussi « installer » des modèles hébergés chez ollama.com
# (suffixe « :cloud » ou « -cloud » ; champs remote_host / remote_model dans
# /api/tags) : le prompt — donc la dictée patient — partirait sur Internet.
# Ils sont exclus partout : liste proposée, configuration, téléchargement,
# appel.
_SUFFIXE_CLOUD_RE = re.compile(r"[:-]cloud$", re.IGNORECASE)


def nom_modele_valide(nom: str) -> bool:
    return bool(_NOM_MODELE_RE.match(nom or ""))


def nom_modele_cloud(nom: str) -> bool:
    """Vrai si le nom désigne un modèle hébergé par Ollama sur Internet."""
    return bool(_SUFFIXE_CLOUD_RE.search((nom or "").strip()))


def modeles_locaux(tags: dict) -> list[str]:
    """Noms des modèles d'une réponse /api/tags qui s'exécutent sur cette
    machine ; les entrées hébergées sont écartées."""
    noms = []
    for m in tags.get("models") or []:
        nom = m.get("name") or m.get("model") or ""
        if not nom or m.get("remote_host") or m.get("remote_model"):
            continue
        if nom_modele_cloud(nom):
            continue
        noms.append(nom)
    return noms


def ram_totale_gio() -> float:
    """RAM physique totale en Gio (0.0 si indéterminable). Sans dépendance."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MemStatus()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return round(stat.ullTotalPhys / (1024 ** 3), 1)
        with open("/proc/meminfo", encoding="ascii", errors="ignore") as f:
            for ligne in f:
                if ligne.startswith("MemTotal:"):
                    kio = int(ligne.split()[1])
                    return round(kio / (1024 ** 2), 1)
    except Exception:
        pass
    return 0.0


def proposition_modele(ram_gio: float) -> dict:
    """Modèle LLM proposé selon la RAM ({modele, raison, deconseille})."""
    if ram_gio and ram_gio < RAM_MINIMALE_GIO:
        return {
            "modele": MODELE_8GO,
            "deconseille": True,
            "raison": f"RAM détectée : {ram_gio} Gio — en dessous du minimum "
                      "recommandé (8 Go). L'application fonctionnera lentement.",
        }
    if ram_gio and ram_gio < 15:
        return {
            "modele": MODELE_8GO,
            "deconseille": False,
            "raison": f"RAM détectée : {ram_gio} Gio — modèle compact conseillé.",
        }
    return {
        "modele": MODELE_16GO,
        "deconseille": False,
        "raison": (f"RAM détectée : {ram_gio} Gio — " if ram_gio else "")
                  + "modèle de meilleure qualité française.",
    }


def ollama_etat(cfg: dict) -> dict:
    """Ollama joignable ? Quels modèles installés ? (timeout court)."""
    host = cfg["llm"].get("host") or "http://localhost:11434"
    try:
        r = httpx.get(f"{host}/api/tags", timeout=2)
        r.raise_for_status()
        return {"ok": True, "modeles": modeles_locaux(r.json())}
    except Exception:
        return {"ok": False, "modeles": []}


def _present(nom: str, modeles: list[str]) -> bool:
    """Un modèle est présent si le nom exact ou son :latest est installé."""
    return nom in modeles or f"{nom}:latest" in modeles or any(
        m.split(":")[0] == nom for m in modeles
    )


def etat_installation(cfg: dict, modele_choisi: str = "") -> dict:
    """Bilan complet pour l'écran de premier lancement.

    ``modele_choisi`` : modèle de remplacement retenu à l'écran quand le
    téléchargement de la proposition a échoué (nom disparu de la bibliothèque,
    disque trop petit). Il remplace alors la proposition, sans quoi l'écran
    resterait bloqué sur un modèle qu'on ne peut pas obtenir."""
    ram = ram_totale_gio()
    prop = proposition_modele(ram)
    if modele_choisi and nom_modele_valide(modele_choisi) and not nom_modele_cloud(modele_choisi):
        prop = {**prop, "modele": modele_choisi, "raison": "modèle choisi à l'installation"}
    ollama = ollama_etat(cfg)
    llm_configure = cfg["llm"]["model"]
    emb = cfg["embeddings"]["model"]
    llm_present = _present(llm_configure, ollama["modeles"])
    # Le LLM est « prêt » si le modèle configuré OU le modèle proposé est là
    # (au premier lancement, l'utilisateur télécharge la proposition puis
    # l'UI la bascule en configuration après le déverrouillage).
    llm_pret = llm_present or _present(prop["modele"], ollama["modeles"])
    emb_present = _present(emb, ollama["modeles"])
    a_telecharger = (0.0 if llm_pret else taille_estimee_go(prop["modele"])) + (
        0.0 if emb_present else taille_estimee_go(emb)
    )
    return {
        "ollama": ollama["ok"],
        "modeles": ollama["modeles"],
        "ram_gio": ram,
        "proposition": prop,
        "llm_configure": llm_configure,
        "llm_present": llm_present,
        "embeddings_configure": emb,
        "embeddings_present": emb_present,
        "pret": ollama["ok"] and llm_pret and emb_present,
        "disque_libre_gio": disque_libre_gio(),
        "taille_a_telecharger_gio": round(a_telecharger, 1),
    }
