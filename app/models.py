"""Modèles d'échange (Pydantic) de l'API.

Phase 0 : modèles de session (déverrouillage, statut, config) et énumérations
du domaine. Les modèles CRUD des bilans/patients seront étoffés en Phase 3.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .systeme import nom_modele_cloud


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


class PassphraseChange(BaseModel):
    """Rotation de la passphrase : l'ancienne sert à vérifier, la nouvelle
    re-chiffre le coffre. Ni l'une ni l'autre n'est journalisée."""
    ancienne: str
    nouvelle: str


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
    # Nouveautés de la version (texte simple tiré des notes de release), date
    # de publication, et ce que le poste peut en faire : installation en un
    # clic (app compilée sous Windows) ou simple lien.
    notes: str = ""
    publiee_le: str = ""
    installation_possible: bool = False
    # La version disponible est celle que le praticien a demandé d'ignorer.
    ignoree: bool = False
    verifiee_le: str = ""


class MajEtatPatch(BaseModel):
    """État local des mises à jour : information vue, version ignorée
    (chaîne vide = ne plus rien ignorer)."""

    info_vue: bool | None = None
    ignoree: str | None = Field(None, max_length=20)


class MajTelechargement(BaseModel):
    version: str = Field(..., max_length=20)


class MajInstallation(BaseModel):
    version: str = Field(..., max_length=20)
    # Port de cette instance : l'installeur relance l'app dessus, et la page
    # ouverte se reconnecte seule (voir lanceur.py --port).
    port: int = Field(..., ge=1, le=65535)


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


def _exiger_modele_local(v: str | None) -> str | None:
    """Un modèle Ollama « cloud » (glm-5.2:cloud, gpt-oss:120b-cloud…) est
    exécuté chez ollama.com : la dictée patient partirait sur Internet."""
    if v is not None and nom_modele_cloud(v):
        raise ValueError(
            "modèle hébergé par Ollama sur Internet (« cloud ») : refusé, les "
            "données patient ne quittent pas la machine"
        )
    return v


class LlmPatch(_SectionPatch):
    model: str | None = None
    temperature: float | None = Field(None, ge=0, le=2)
    host: str | None = None
    num_ctx: int | None = Field(None, ge=256)
    timeout_s: float | None = Field(None, ge=10)
    max_car_section: int | None = Field(None, ge=100)

    _host_local = field_validator("host")(_exiger_hote_local)
    _modele_local = field_validator("model")(_exiger_modele_local)


class EmbeddingsPatch(_SectionPatch):
    model: str | None = None
    host: str | None = None

    _host_local = field_validator("host")(_exiger_hote_local)
    _modele_local = field_validator("model")(_exiger_modele_local)


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
    """Seuils de drapeaux. Les seuils en écart-type sont des seuils *bas* :
    saisir 1.5 au lieu de -1.5 basculait tous les résultats normaux en « zone de
    fragilité », sans un mot. D'où les bornes, et le contrôle d'ordre :
    sévère ≤ pathologique ≤ fragilité (et l'inverse en percentile)."""

    fragilite_et: float | None = Field(None, ge=-6, le=0)
    pathologique_et: float | None = Field(None, ge=-6, le=0)
    severe_et: float | None = Field(None, ge=-6, le=0)
    fragilite_percentile: float | None = Field(None, ge=0, le=100)
    pathologique_percentile: float | None = Field(None, ge=0, le=100)
    severe_percentile: float | None = Field(None, ge=0, le=100)

    @model_validator(mode="after")
    def _ordre_coherent(self):
        # Contrôle deux à deux, sur les seuls champs fournis : les surcharges
        # sont partielles (fusion profonde côté serveur).
        paires = [
            ("severe_et", "pathologique_et"), ("pathologique_et", "fragilite_et"),
            ("severe_percentile", "pathologique_percentile"),
            ("pathologique_percentile", "fragilite_percentile"),
        ]
        for bas, haut in paires:
            a, b = getattr(self, bas), getattr(self, haut)
            if a is not None and b is not None and a > b:
                raise ValueError(
                    f"seuils incohérents : {bas} ({a}) doit rester inférieur ou égal "
                    f"à {haut} ({b}) — sinon les drapeaux ne veulent plus rien dire"
                )
        return self


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


class PraticienPatch(_SectionPatch):
    """Identité professionnelle portée sur les exports. Bornes de longueur
    seulement : ni ADELI ni RPPS ne sont validés sur leur format, l'app n'a pas
    à refuser un identifiant que l'Assurance maladie accepterait."""

    nom: str | None = Field(None, max_length=120)
    prenom: str | None = Field(None, max_length=120)
    titre: str | None = Field(None, max_length=120)
    adeli: str | None = Field(None, max_length=40)
    rpps: str | None = Field(None, max_length=40)
    siret: str | None = Field(None, max_length=40)
    adresse: str | None = Field(None, max_length=300)
    code_postal: str | None = Field(None, max_length=20)
    ville: str | None = Field(None, max_length=120)
    telephone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=200)
    lieu_signature: str | None = Field(None, max_length=120)


POSITIONS_LOGO = ("gauche", "centre", "droite")


class MiseEnPagePatch(_SectionPatch):
    """Mise en page des exports. Bornes larges mais fermes : une taille de
    corps à 40 points ou une marge de 90 mm ne produisent plus un document,
    et une couleur libre finirait dans le balisage du PDF."""

    police: str | None = Field(None, min_length=1, max_length=60)
    taille_corps: float | None = Field(None, ge=8, le=16)
    interligne: float | None = Field(None, ge=0.8, le=2.5)
    marges_mm: float | None = Field(None, ge=5, le=40)
    couleur_titres: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    rubriques_numerotees: bool | None = None
    numeros_de_page: bool | None = None
    logo_position: Literal["gauche", "centre", "droite"] | None = None
    logo_hauteur_mm: float | None = Field(None, ge=5, le=60)

    @model_validator(mode="before")
    @classmethod
    def _logo_par_sa_route(cls, data):
        # Le logo est une image validée et redimensionnée par PUT /api/config/logo ;
        # accepté ici, n'importe quel texte deviendrait « l'image » de l'en-tête.
        if isinstance(data, dict) and "logo" in data:
            raise ValueError(
                "le logo se dépose par PUT /api/config/logo (fichier image), "
                "pas dans les réglages"
            )
        return data


class OverridesPatch(_SectionPatch):
    praticien: PraticienPatch | None = None
    mise_en_page: MiseEnPagePatch | None = None
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

    @model_validator(mode="after")
    def _cles_uniques(self):
        """Deux rubriques de même clé : le compte-rendu imprimait la rubrique
        deux fois, et le texte de l'IA n'atterrissait que dans l'une d'elles."""
        vues = set()
        for s in self.sections:
            cle = s.cle.strip().lower()
            if cle in vues:
                raise ValueError(
                    f"clé de rubrique en double : « {s.cle} » — chaque rubrique "
                    "doit porter une clé distincte"
                )
            vues.add(cle)
        return self


class TestCatalogue(BaseModel):
    model_config = ConfigDict(extra="allow")

    nom: str
    tranche: str = ""
    mesure: str = ""
    metriques: list[
        Literal["ecart_type", "percentile", "note_standard", "note_standard_100",
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

def _date_iso_ou_vide(v: str | None) -> str:
    """Date au format AAAA-MM-JJ, ou chaîne vide. Une date invalide est refusée
    plutôt que reportée telle quelle sur un document adressé au prescripteur."""
    v = (v or "").strip()
    if not v:
        return ""
    try:
        date.fromisoformat(v)
    except ValueError:
        raise ValueError("date attendue au format AAAA-MM-JJ")
    return v


class BilanCreate(BaseModel):
    domaines: list[str] = []
    type: BilanType = BilanType.initial_simple
    patient_id: int | None = None
    motif: str = ""
    # Vide = date du jour (la date de rédaction n'est pas celle de la séance
    # quand le compte-rendu est rédigé plus tard).
    date_bilan: str = ""
    prescripteur: str = Field("", max_length=200)
    prescripteur_rpps: str = Field("", max_length=40)

    _date = field_validator("date_bilan")(_date_iso_ou_vide)


class BilanPatch(BaseModel):
    """En-tête modifiable d'un bilan : date et prescripteur (champ absent =
    inchangé)."""

    date_bilan: str | None = None
    prescripteur: str | None = Field(None, max_length=200)
    prescripteur_rpps: str | None = Field(None, max_length=40)

    @field_validator("date_bilan")
    @classmethod
    def _valide_date(cls, v: str | None) -> str | None:
        return None if v is None else _date_iso_ou_vide(v)


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
    # note_standard = moyenne 10 / ET 3 ; note_standard_100 = moyenne 100 / ET 15
    etalonnage_type: str | None = None   # ecart_type|percentile|note_standard[_100]|age_dev|age_lecture
    etalonnage_valeur: str | None = None
    percentile: str | None = None
    note_standard: str | None = None
    age_dev: str | None = None
    interpretation: str | None = None
    drapeau_seuil: str | None = None     # laissé vide -> déduit des seuils

    def exploitable(self) -> bool:
        """Vrai si le résultat porte quelque chose de restituable.

        Un corps sans résultat utile créait une épreuve coquille : une ligne
        vide dans le tableau du compte-rendu, qu'aucune route ne permettait de
        retirer."""
        champs = ("score_brut", "etalonnage_valeur", "interpretation",
                  "percentile", "note_standard", "age_dev")
        return any((getattr(self, c) or "").strip() for c in champs)


class EpreuveCreate(BaseModel):
    test_nom: str
    domaine: str = ""
    version: str = ""
    resultats: list[ResultatIn] = []

    @model_validator(mode="after")
    def _au_moins_un_resultat(self):
        if not any(r.exploitable() for r in self.resultats):
            raise ValueError(
                "une épreuve doit porter au moins un résultat exploitable "
                "(score brut, valeur d'étalonnage ou interprétation)"
            )
        return self


