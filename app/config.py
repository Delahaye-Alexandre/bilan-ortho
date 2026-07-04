"""Couche de configuration de bilan-ortho.

Deux niveaux :
- **Config applicative** (non sensible) : emplacement des données, hôte/port,
  hôte Ollama. Lue depuis l'environnement / valeurs par défaut.
- **Config praticien** (surcharges) : stockée *dans la base chiffrée* (table
  ``config``) et fusionnée par-dessus ``DEFAULTS``. C'est le socle de la
  configurabilité : presque tout est paramétrable sans toucher au code.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import db as _db

# --- Config applicative (non sensible) --------------------------------------

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
APP_HOST = os.environ.get("BILAN_ORTHO_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("BILAN_ORTHO_PORT", "8000"))


def _data_dir_defaut() -> Path:
    """Emplacement par défaut des données, selon l'OS."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "bilan-ortho"
    return Path.home() / ".local/share/bilan-ortho"


def data_dir() -> Path:
    """Répertoire des données (créé au besoin). Hors du dépôt git par défaut."""
    d = Path(os.environ.get("BILAN_ORTHO_DATA_DIR") or _data_dir_defaut())
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "bilan.db"


def audio_dir() -> Path:
    d = data_dir() / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- Domaines d'intervention orthophonique (entité pivot) -------------------
# Le domaine conditionne trame, tests, cotation et vocabulaire. Les trames et
# catalogues de tests détaillés arrivent en Phase 3 (données dans data/).

DOMAINES: list[dict[str, str]] = [
    {"cle": "langage_oral", "titre": "Langage oral"},
    {"cle": "langage_ecrit", "titre": "Langage écrit (lecture / orthographe)"},
    {"cle": "parole_articulation", "titre": "Parole / articulation / phonologie"},
    {"cle": "cognition_mathematique", "titre": "Cognition mathématique"},
    {"cle": "communication_tsa", "titre": "Communication & handicap / TSA"},
    {"cle": "voix", "titre": "Voix"},
    {"cle": "deglutition_omf", "titre": "Déglutition / fonctions oro-myo-faciales"},
    {"cle": "neuro_acquise", "titre": "Neurologie acquise (aphasie, dysarthrie, neurodégénératif)"},
    {"cle": "surdite", "titre": "Surdité"},
    {"cle": "begaiement", "titre": "Bégaiement / fluence"},
    {"cle": "oralite_nourrisson", "titre": "Oralité alimentaire du nourrisson"},
]


# --- Valeurs par défaut (surchargées par la config praticien) ---------------

DEFAULTS: dict[str, Any] = {
    "llm": {
        "model": "qwen2.5:7b-instruct-q4_K_M",
        "temperature": 0.3,
        "host": OLLAMA_HOST,
    },
    "stt": {
        # "auto" -> stt.py détecte GPU/VRAM et choisit le modèle adapté.
        # Pour la meilleure qualité FR, renseigner un dépôt/chemin CTranslate2
        # du modèle fine-tuné FR (ex. conversion de bofenghuang/whisper-large-v3-french).
        "device": "auto",          # auto | cuda | cpu
        "model": "auto",           # auto | tiny|base|small|medium|large-v3 | <repo/chemin CT2>
        "compute_type": "auto",    # auto | float16 | int8_float16 | int8
        "language": "fr",
        "vad": True,               # coupe les silences (VAD Silero)
        "beam_size": 5,
        # Biais de vocabulaire métier (faster-whisper `hotwords`).
        "hotwords": [
            "orthophonie", "orthophonique", "bilan", "anamnèse", "phonologie",
            "phonologique", "praxies", "articulation", "morphosyntaxe", "lexique",
            "dénomination", "conscience phonologique", "métaphonologie",
            "dyslexie", "dysorthographie", "dyscalculie", "dysphasie",
            "trouble développemental du langage", "logico-mathématique",
            "écart-type", "percentile", "note standard", "âge de lecture",
            "Alouette", "EVALEO", "EXALANG", "ELO", "BALE", "ODEDYS", "TEDI-MATH",
            "MBLF", "N-EEL", "L2MA", "ZAREKI", "déglutition", "oralité", "dysphonie",
            "aphasie", "dysarthrie", "bégaiement", "fluence",
        ],
        # Corrections déterministes appliquées après transcription (regex sensibles
        # à la casse par défaut ; clé -> remplacement).
        "corrections": {},
    },
    "embeddings": {
        # nomic-embed-text : léger (~274 Mo), fonctionne partout. Pour une meilleure
        # qualité FR, passer à "bge-m3" (~1,2 Go, `ollama pull bge-m3`).
        "model": "nomic-embed-text",
        "host": OLLAMA_HOST,
    },
    "rgpd": {
        # NB : l'audio de dictée est TOUJOURS supprimé après transcription
        # (stt.py) — ce n'est volontairement pas un réglage.
        "verrouillage_inactivite_minutes": 15,
        "conservation_jours": 0,   # 0 = pas de purge automatique
    },
    "sauvegarde": {
        # Copie chiffrée du coffre (même passphrase). Vide = <données>/sauvegardes.
        "dossier": "",
        "retention": 10,           # nb de copies conservées (rotation)
        "auto_jours": 7,           # auto au déverrouillage si plus ancienne ; 0 = off
    },
    "style": {
        "few_shot_k": 4,           # nb d'extraits du praticien réinjectés (RAG)
        "vouvoiement": True,
        "niveau_detail": "standard",  # concis | standard | detaille
    },
    "seuils": {
        # Écarts-types (recherche : -1,5 ET = zone patho standard).
        "fragilite_et": -1.0,
        "pathologique_et": -1.5,
        "severe_et": -2.0,
    },
    "cotation": {
        # NGAP — évolue par avenants (source de vérité : ameli.fr). Paramétrable.
        "valeur_amo": 2.60,
        "bilan_simple_coeff": 24,
        "bilan_complexe_coeff": 34,
        "renouvellement_coeff": 30,
    },
    "trame": {
        # Rubriques créées pour chaque nouveau bilan (clé + intitulé, dans
        # l'ordre). Surchargeable depuis Paramètres → Avancé.
        "sections": [
            {"cle": c, "titre": t} for c, t in _db.SECTIONS_TRONC_COMMUN
        ],
    },
    # Surcharges des catalogues de tests, par clé de domaine :
    # {"langage_ecrit": {"guidance": "...", "tests": [{"nom": ..., ...}]}}
    "catalogues": {},
    "prompts": {
        # Vide = prompt de structuration par défaut (prompts.STRUCTURE_SYSTEM).
        # Dans un prompt personnalisé, {cles} est remplacé par les clés valides.
        "structure_system": "",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class ConfigStore:
    """Lit/écrit les surcharges de config dans la base chiffrée (table config)."""

    KEY = "overrides"

    def __init__(self, con):
        self._con = con

    def overrides(self) -> dict:
        row = self._con.execute(
            "SELECT value FROM config WHERE key = ?", (self.KEY,)
        ).fetchone()
        return json.loads(row[0]) if row else {}

    def effective(self) -> dict:
        """DEFAULTS fusionné avec les surcharges praticien."""
        return _deep_merge(DEFAULTS, self.overrides())

    def set_overrides(self, override: dict) -> dict:
        """Fusionne de nouvelles surcharges et persiste. Retourne l'effectif."""
        merged = _deep_merge(self.overrides(), override)
        self._con.execute(
            "INSERT INTO config(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self.KEY, json.dumps(merged, ensure_ascii=False)),
        )
        return _deep_merge(DEFAULTS, merged)

    def reset(self) -> dict:
        """Efface toutes les surcharges praticien. Retourne les défauts."""
        self._con.execute("DELETE FROM config WHERE key = ?", (self.KEY,))
        return copy.deepcopy(DEFAULTS)
