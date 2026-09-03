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
import ipaddress
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
    restreindre_acces(d, 0o700)
    return d


def restreindre_acces(chemin, mode: int = 0o600) -> None:
    """Réserve un fichier ou un dossier du coffre à son propriétaire.

    Le chiffrement protège le contenu, pas la copie : sur un poste de cabinet
    ou un ordinateur familial, un fichier lisible par les autres comptes se
    recopie en une commande et se casse ensuite hors ligne, à loisir. Le
    registre RGPD annonce le chiffrement au repos sans cette réserve.

    Best-effort volontaire : FAT/exFAT (dossier de sauvegarde sur clé USB) et
    Windows ignorent ``chmod``, et un échec ne doit jamais empêcher d'écrire
    une sauvegarde."""
    try:
        os.chmod(chemin, mode)
    except OSError:
        pass


def db_path() -> Path:
    return data_dir() / "bilan.db"


def hote_est_local(url: str) -> bool:
    """True si l'URL pointe sur la machine locale (loopback).

    Des données de santé transitent vers ``llm.host`` / ``embeddings.host`` :
    en cohérence avec le registre RGPD (traitement 100 % local), ces hôtes
    sont contraints à 127.0.0.0/8, ::1 ou localhost."""
    if not url or not str(url).strip():
        return True  # vide -> défaut local
    try:
        h = urlparse(url if "://" in str(url) else f"http://{url}").hostname
    except ValueError:
        return False
    if not h:
        return False
    if h == "localhost":
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        pass  # nom d'hôte : on résout et on exige que TOUT pointe en local
    try:
        infos = socket.getaddrinfo(h, None)
    except OSError:
        return False
    return bool(infos) and all(
        ipaddress.ip_address(i[4][0]).is_loopback for i in infos
    )


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
    # Identité professionnelle, reportée en en-tête et en signature des exports.
    # Un compte-rendu de bilan orthophonique est adressé au prescripteur : sans
    # ces mentions, le praticien devait recoller le texte dans son papier à
    # en-tête, ce qui annulait le temps gagné. Tout est vide par défaut — un
    # en-tête n'apparaît que s'il a été renseigné, jamais d'identité inventée.
    "praticien": {
        "nom": "",
        "prenom": "",
        "titre": "Orthophoniste",
        "adeli": "",
        "rpps": "",
        "siret": "",
        "adresse": "",
        "code_postal": "",
        "ville": "",
        "telephone": "",
        "email": "",
        # Lieu porté sur la formule « Fait à …, le … ». Vide = la ville.
        "lieu_signature": "",
    },
    # Mise en page des documents exportés (Word et PDF) : police, corps,
    # interligne, marges, couleur des titres, numérotation des rubriques,
    # numéros de page, logo. Lot B du plan « mise en forme » : jusqu'ici tout
    # était en dur dans export.py et le praticien finissait dans Word. Le logo
    # (PNG/JPEG en base64) se dépose par PUT /api/config/logo, jamais par le
    # PUT général. Les polices sont celles de Word ; le PDF prend la même quand
    # le fichier de police est trouvé sur la machine, sinon l'équivalente
    # intégrée (Helvetica ou Times) — voir export._polices_pdf.
    "mise_en_page": {
        "police": "Calibri",
        "taille_corps": 11,          # points
        "interligne": 1.15,          # multiple (1 = simple)
        "marges_mm": 20,
        "couleur_titres": "#000000",
        "rubriques_numerotees": False,
        "numeros_de_page": True,
        "logo": None,                # {"type": "image/png", "donnees": base64, ...}
        "logo_position": "gauche",   # gauche | centre | droite
        "logo_hauteur_mm": 20,
    },
    "llm": {
        "model": "qwen2.5:7b-instruct-q4_K_M",
        "temperature": 0.3,
        "host": OLLAMA_HOST,
        # Fenêtre de contexte demandée à Ollama : le prompt de structuration
        # embarque le contenu des rubriques + la mémoire du dialogue ; sans
        # cette option, Ollama tronque silencieusement au défaut (~4k).
        "num_ctx": 8192,
        # Attente maximale d'une structuration (secondes). Sans borne, un
        # Ollama gelé suspendait l'interface à l'infini.
        "timeout_s": 600,
        # Au-delà de ce nombre de caractères, le contenu d'une rubrique n'est
        # transmis que partiellement au modèle (début conservé) ; la réponse
        # de /structure signale les rubriques concernées.
        "max_car_section": 1500,
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
        # Corrections déterministes appliquées après transcription : mot entier,
        # casse ignorée (clé -> remplacement) ; préfixe « re: » pour une regex
        # (voir stt._apply_corrections).
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
        # Durée maximale d'une dictée (le ping de dictée maintient le coffre
        # déverrouillé : sans borne, un micro oublié neutraliserait le
        # verrouillage d'inactivité). 0 = sans limite.
        "dictee_max_minutes": 30,
    },
    "sauvegarde": {
        # Copie chiffrée du coffre (même passphrase). Vide = <données>/sauvegardes.
        "dossier": "",
        "retention": 10,           # nb de copies conservées (rotation)
        "auto_jours": 7,           # auto au déverrouillage si plus ancienne ; 0 = off
    },
    "maj": {
        # Vérification des mises à jour au démarrage : au plus une fois par
        # jour, un simple GET vers GitHub Releases, aucune donnée transmise
        # (voir app/maj.py). Activée par défaut depuis la 1.10.0 (décision du
        # 2026-09-03 : personne ne se mettait à jour) ; l'app le dit une fois
        # après le déverrouillage et le réglage reste désactivable. Le bouton
        # « Vérifier maintenant » des Paramètres ignore ce réglage.
        "verification_auto": True,
    },
    "style": {
        "few_shot_k": 4,           # nb d'extraits du praticien réinjectés (RAG)
        "vouvoiement": True,
        "niveau_detail": "standard",  # concis | standard | detaille
        # Le modèle peut mettre en forme (gras, italique, souligné, listes),
        # sobrement et en calquant les bilans de référence. Désactivé : ses
        # textes sont remis en clair avant d'entrer dans les rubriques.
        "mise_en_forme_ia": True,
    },
    "seuils": {
        # Écarts-types (recherche : -1,5 ET = zone patho standard).
        "fragilite_et": -1.0,
        "pathologique_et": -1.5,
        "severe_et": -2.0,
        # Équivalents percentile (mêmes zones, autre étalonnage).
        "fragilite_percentile": 16,
        "pathologique_percentile": 7,
        "severe_percentile": 2,
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
        # l'ordre). Surchargeable depuis Paramètres → Trame des bilans.
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
        self._persister(merged)
        return _deep_merge(DEFAULTS, merged)

    def remplacer_section(self, cle: str, valeur) -> dict:
        """Remplace la surcharge d'une section EN BLOC (aucune fusion) : la
        fusion profonde de set_overrides ne sait ni retirer un élément d'une
        liste ni supprimer un domaine surchargé. Retourne l'effectif."""
        ov = self.overrides()
        ov[cle] = copy.deepcopy(valeur)
        self._persister(ov)
        return _deep_merge(DEFAULTS, ov)

    def effacer_section(self, cle: str) -> dict:
        """Supprime la surcharge d'une section : retour aux défauts, qui
        suivent les mises à jour de l'application. Retourne l'effectif."""
        ov = self.overrides()
        ov.pop(cle, None)
        if ov:
            self._persister(ov)
        else:
            self._con.execute("DELETE FROM config WHERE key = ?", (self.KEY,))
        return _deep_merge(DEFAULTS, ov)

    def effacer_cles(self, cle: str, cles: list[str]) -> dict:
        """Retire quelques clés de la surcharge d'une section (retour aux défauts
        pour elles seules). L'écran Paramètres répartit une même section entre
        « Ma dictée » (vocabulaire, corrections) et les réglages techniques
        (matériel, modèle…) : chacun revient à ses valeurs sans l'autre.
        Retourne l'effectif."""
        ov = self.overrides()
        section = ov.get(cle)
        if isinstance(section, dict):
            for k in cles:
                section.pop(k, None)
            if not section:
                ov.pop(cle, None)
        if ov:
            self._persister(ov)
        else:
            self._con.execute("DELETE FROM config WHERE key = ?", (self.KEY,))
        return _deep_merge(DEFAULTS, ov)

    def reset(self) -> dict:
        """Efface toutes les surcharges praticien. Retourne les défauts."""
        self._con.execute("DELETE FROM config WHERE key = ?", (self.KEY,))
        return copy.deepcopy(DEFAULTS)

    def _persister(self, ov: dict) -> None:
        self._con.execute(
            "INSERT INTO config(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self.KEY, json.dumps(ov, ensure_ascii=False)),
        )
