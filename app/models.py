"""Modèles d'échange (Pydantic) de l'API.

Phase 0 : modèles de session (déverrouillage, statut, config) et énumérations
du domaine. Les modèles CRUD des bilans/patients seront étoffés en Phase 3.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class BilanType(str, Enum):
    initial_simple = "initial_simple"
    initial_complexe = "initial_complexe"
    renouvellement = "renouvellement"


class BilanStatut(str, Enum):
    brouillon = "brouillon"
    valide = "valide"
    envoye = "envoye"


class SectionStatut(str, Enum):
    vide = "vide"
    propose_ia = "propose_ia"
    valide = "valide"


# --- Session / sécurité ------------------------------------------------------

class UnlockRequest(BaseModel):
    passphrase: str


class StatusResponse(BaseModel):
    db_exists: bool
    unlocked: bool
    first_run: bool
    version: str = ""


class OkResponse(BaseModel):
    ok: bool
    detail: str = ""


# --- Configuration -----------------------------------------------------------

class ConfigPatch(BaseModel):
    """Surcharges partielles de configuration (fusion profonde côté serveur)."""

    overrides: dict


# --- Bilans / structuration --------------------------------------------------

class BilanCreate(BaseModel):
    domaines: list[str] = []
    type: BilanType = BilanType.initial_simple
    patient_id: int | None = None
    motif: str = ""


class StructureRequest(BaseModel):
    transcription: str


class SectionPut(BaseModel):
    contenu: str
    statut: SectionStatut | None = None


class StatutPut(BaseModel):
    """Évolution du cycle de vie du bilan (validation, envoi au prescripteur)."""

    statut: BilanStatut
    destinataire: str = ""


class PatientIn(BaseModel):
    """Identité minimale d'un patient (création / mise à jour)."""

    nom: str
    prenom: str = ""
    date_naissance: str = ""   # ISO AAAA-MM-JJ (ou JJ/MM/AAAA accepté)
    sexe: str = ""
    notes: str = ""


class ResultatIn(BaseModel):
    sous_epreuve: str | None = None
    score_brut: str | None = None
    etalonnage_type: str | None = None   # ecart_type|percentile|note_standard|age_dev|age_lecture
    etalonnage_valeur: str | None = None
    percentile: str | None = None
    note_standard: str | None = None
    age_dev: str | None = None
    interpretation: str | None = None
    drapeau_seuil: str | None = None     # laissé vide -> déduit des seuils


class EpreuveCreate(BaseModel):
    test_nom: str
    domaine: str = ""
    version: str = ""
    resultats: list[ResultatIn] = []


# --- Génération (existant, conservé) ----------------------------------------

class GenerateRequest(BaseModel):
    section: str
    notes: str
    contexte: str = ""
    model: str | None = None
    temperature: float = 0.3
