"""État du système pour le premier lancement guidé : RAM disponible,
présence d'Ollama et des modèles, proposition de modèle adaptée à la machine.

Aucune donnée patient ici : ces fonctions s'exécutent avant même la création
du coffre.
"""
from __future__ import annotations

import re
import sys

import httpx

# Défauts distribués (recherche juillet 2026, benchmark FR CARTE ; licences
# Apache 2.0). La proposition suit la RAM totale de la machine.
MODELE_16GO = "qwen3.5:9b"      # ~5,5 Go q4 — qualité FR maximale du format
MODELE_8GO = "qwen3.5:4b"       # ~2,4 Go q4 — pour les machines modestes
RAM_MINIMALE_GIO = 7.0          # en dessous : app déconseillée

_NOM_MODELE_RE = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")


def nom_modele_valide(nom: str) -> bool:
    return bool(_NOM_MODELE_RE.match(nom or ""))


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
        modeles = [m["name"] for m in r.json().get("models", [])]
        return {"ok": True, "modeles": modeles}
    except Exception:
        return {"ok": False, "modeles": []}


def _present(nom: str, modeles: list[str]) -> bool:
    """Un modèle est présent si le nom exact ou son :latest est installé."""
    return nom in modeles or f"{nom}:latest" in modeles or any(
        m.split(":")[0] == nom for m in modeles
    )


def etat_installation(cfg: dict) -> dict:
    """Bilan complet pour l'écran de premier lancement."""
    ram = ram_totale_gio()
    prop = proposition_modele(ram)
    ollama = ollama_etat(cfg)
    llm_configure = cfg["llm"]["model"]
    emb = cfg["embeddings"]["model"]
    llm_present = _present(llm_configure, ollama["modeles"])
    # Le LLM est « prêt » si le modèle configuré OU le modèle proposé est là
    # (au premier lancement, l'utilisateur télécharge la proposition puis
    # l'UI la bascule en configuration après le déverrouillage).
    llm_pret = llm_present or _present(prop["modele"], ollama["modeles"])
    emb_present = _present(emb, ollama["modeles"])
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
    }
