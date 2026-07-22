"""Modèles d'échange (Pydantic) de l'API.

Phase 0 : modèles de session (déverrouillage, statut, config) et énumérations
du domaine. Les modèles CRUD des bilans/patients seront étoffés en Phase 3.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class RestaurationRequest(BaseModel):
    """Restauration d'une sauvegarde : nom de fichier (jamais un chemin) +
    passphrase, indispensable pour vérifier la copie et rouvrir le coffre."""
    fichier: str
    passphrase: str


class StatusResponse(BaseModel):
    db_exists: bool
    unlocked: bool
    first_run: bool
    version: str = ""


class OkResponse(BaseModel):
    ok: bool
    detail: str = ""


class MajResponse(BaseModel):
    """Résultat de la vérification de mise à jour (app/maj.py)."""

    version_actuelle: str
    version_disponible: str
    maj_disponible: bool
    url: str


# --- Configuration -----------------------------------------------------------
#
# Les surcharges sont validées : une valeur mal typée (« 15 » au lieu de 15)
# était fusionnée telle quelle et faisait planter toutes les routes protégées
# au premier calcul (app « briquée »). Les clés connues sont typées (avec
# coercition tolérante : "15" -> 15) ; les clés inconnues restent acceptées
# pour ne pas casser les configurations avancées.

def _exiger_hote_local(v: str | None) -> str | None:
    from . import config

    if v is not None and not config.hote_est_local(v):
        raise ValueError(
            "hôte non local refusé — les données de santé doivent rester "
            "sur cette machine (127.0.0.1 / localhost)."
        )
    return v


class _SectionPatch(BaseModel):
    model_config = ConfigDict(extra="allow")


class LlmPatch(_SectionPatch):
    model: str | None = None
    temperature: float | None = Field(None, ge=0, le=2)
    host: str | None = None
    num_ctx: int | None = Field(None, ge=256)
    timeout_s: float | None = Field(None, ge=10)
    max_car_section: int | None = Field(None, ge=100)

    _host_local = field_validator("host")(_exiger_hote_local)


class EmbeddingsPatch(_SectionPatch):
    model: str | None = None
    host: str | None = None

    _host_local = field_validator("host")(_exiger_hote_local)


class SttPatch(_SectionPatch):
    device: str | None = None
    model: str | None = None
    compute_type: str | None = None
    language: str | None = None
    vad: bool | None = None
    beam_size: int | None = Field(None, ge=1, le=10)
    hotwords: list[str] | None = None
    corrections: dict[str, str] | None = None


class RgpdPatch(_SectionPatch):
    verrouillage_inactivite_minutes: float | None = Field(None, ge=0)
    conservation_jours: int | None = Field(None, ge=0)
    # Plafond à 7 jours : au-delà, le délai en ms dépasserait l'int32 de
    # setTimeout côté navigateur (débordement = arrêt immédiat de la dictée).
    dictee_max_minutes: float | None = Field(None, ge=0, le=10080)


class SauvegardePatch(_SectionPatch):
    dossier: str | None = None
    retention: int | None = Field(None, ge=0)
    auto_jours: int | None = Field(None, ge=0)


class StylePatch(_SectionPatch):
    few_shot_k: int | None = Field(None, ge=0, le=20)
    vouvoiement: bool | None = None
    niveau_detail: str | None = None


class SeuilsPatch(_SectionPatch):
    fragilite_et: float | None = None
    pathologique_et: float | None = None
    severe_et: float | None = None
    fragilite_percentile: float | None = Field(None, ge=0, le=100)
    pathologique_percentile: float | None = Field(None, ge=0, le=100)
    severe_percentile: float | None = Field(None, ge=0, le=100)


class CotationPatch(_SectionPatch):
    valeur_amo: float | None = Field(None, ge=0)
    bilan_simple_coeff: float | None = Field(None, ge=0)
    bilan_complexe_coeff: float | None = Field(None, ge=0)
    renouvellement_coeff: float | None = Field(None, ge=0)


class TrameSectionPatch(_SectionPatch):
    cle: str
    titre: str


class TramePatch(_SectionPatch):
    sections: list[TrameSectionPatch] | None = None


class PromptsPatch(_SectionPatch):
    structure_system: str | None = None


class MajPatch(_SectionPatch):
    verification_auto: bool | None = None


class OverridesPatch(_SectionPatch):
    llm: LlmPatch | None = None
    stt: SttPatch | None = None
    embeddings: EmbeddingsPatch | None = None
    rgpd: RgpdPatch | None = None
    sauvegarde: SauvegardePatch | None = None
    style: StylePatch | None = None
    seuils: SeuilsPatch | None = None
    cotation: CotationPatch | None = None
    trame: TramePatch | None = None
    catalogues: dict | None = None
    prompts: PromptsPatch | None = None
    maj: MajPatch | None = None


class ConfigPatch(BaseModel):
    """Surcharges partielles de configuration (fusion profonde côté serveur)."""

    overrides: OverridesPatch


# --- Éditeurs dédiés (remplacement EN BLOC d'une section) ---------------------
#
# Contrairement aux *Patch ci-dessus (fusion tolérante), ces modèles valident
# strictement ce que les éditeurs de l'écran Paramètres envoient : la fusion
# profonde ne sachant rien supprimer, ces routes remplacent la section entière.

def _exiger_non_blanc(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("ne doit pas être vide")
    return v


class TrameSectionStricte(BaseModel):
    model_config = ConfigDict(extra="allow")

    cle: str
    titre: str

    _non_blanc = field_validator("cle", "titre")(_exiger_non_blanc)


class TrameRemplacement(BaseModel):
    """Trame complète (PUT /api/config/trame). Liste vide refusée : pour
    revenir à la trame réglementaire, utiliser DELETE."""

    sections: list[TrameSectionStricte] = Field(min_length=1)


class TestCatalogue(BaseModel):
    model_config = ConfigDict(extra="allow")

    nom: str
    tranche: str = ""
    mesure: str = ""
    metriques: list[
        Literal["ecart_type", "percentile", "note_standard",
                "age_dev", "age_lecture", "qualitatif"]
    ] = []

    _nom_non_blanc = field_validator("nom")(_exiger_non_blanc)


class CatalogueDomaine(BaseModel):
    """Surcharge d'un domaine de catalogue : guidance et/ou tests (chaque
    champ absent conserve la partie intégrée correspondante)."""

    model_config = ConfigDict(extra="allow")

    guidance: str | None = None
    tests: list[TestCatalogue] | None = None


class PromptRemplacement(BaseModel):
    """Prompt de structuration personnalisé ('' = consigne intégrée)."""

    structure_system: str = ""


# --- Bilans / structuration --------------------------------------------------

class BilanCreate(BaseModel):
    domaines: list[str] = []
    type: BilanType = BilanType.initial_simple
    patient_id: int | None = None
    motif: str = ""


class ReponseClarification(BaseModel):
    """Réponse du praticien à une question de clarification posée par l'IA."""

    question: str
    reponse: str
    section: str = ""   # rubrique visée par la question d'origine (indice de routage)


class StructureRequest(BaseModel):
    """Un passage de structuration : dictée libre et/ou réponses aux questions.

    Les listes de questions donnent au LLM la mémoire du dialogue : il ne doit
    ni reposer une question encore affichée (`questions_en_attente`), ni une
    question écartée par le praticien (`questions_ecartees`), ni une question
    dont la réponse vient d'être intégrée (`questions_repondues`)."""

    transcription: str = ""
    reponses: list[ReponseClarification] = []
    questions_en_attente: list[str] = []
    questions_ecartees: list[str] = []
    questions_repondues: list[str] = []


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


