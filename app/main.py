"""Serveur FastAPI — assistant local de rédaction de bilans orthophoniques.

100 % local (bind 127.0.0.1). Les fonctions manipulant des données patient sont
protégées par un déverrouillage (base chiffrée). La génération de texte à partir
de notes reste disponible (elle ne touche pas la base).
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
import sqlcipher3
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import (
    __version__,
    anonymisation,
    bilan,
    catalogues,
    config,
    cotation,
    export,
    importer,
    llm,
    maj,
    patient,
    prompts,
    rag,
    sauvegarde,
    security,
    stt,
    systeme,
    texte_riche,
    verif_chiffres,
    verif_tests,
    verif_texte,
)
from .models import (
    BilanCreate,
    BilanPatch,
    CatalogueDomaine,
    ConfigPatch,
    EpreuveCreate,
    MajEtatPatch,
    MajInstallation,
    MajResponse,
    MajTelechargement,
    MiseEnPagePatch,
    OkResponse,
    PassphraseChange,
    PatientIn,
    PromptRemplacement,
    RestaurationRequest,
    SectionPut,
    StatusResponse,
    StatutPut,
    StructureRequest,
    TrameRemplacement,
    UnlockRequest,
)

STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)

app = FastAPI(title="Bilan Ortho", version=__version__)


@app.exception_handler(security.CoffreVerrouille)
async def coffre_verrouille_handler(request, exc: security.CoffreVerrouille):
    """Le coffre s'est verrouillé entre ``require_unlock`` et ``transaction()``
    (course multi-onglets via POST /api/lock) : 423 sur TOUTES les routes,
    plutôt qu'un 500 opaque — l'interface ré-affiche l'écran de verrouillage."""
    return JSONResponse(status_code=423, content={"detail": "Application verrouillée."})


@app.exception_handler(sauvegarde.SupportIntrouvable)
async def support_introuvable_handler(request, exc: sauvegarde.SupportIntrouvable):
    """Dossier de sauvegarde sur un support non monté (clé USB débranchée) :
    400 avec un message actionnable, plutôt qu'une arborescence fabriquée en
    silence sur le disque interne."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# La base chiffrée lève les exceptions de sqlcipher3, distinctes de celles du
# module sqlite3 standard : les deux classes sont mappées.
@app.exception_handler(sqlite3.OperationalError)
@app.exception_handler(sqlcipher3.OperationalError)
async def sqlite_operationnel_handler(request, exc):
    """Échec d'écriture SQLite (disque plein, typiquement) : message
    actionnable plutôt qu'un 500 opaque."""
    logger.error("Erreur SQLite : %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Écriture impossible (espace disque insuffisant ?). "
                           "Libérez de l'espace puis réessayez."},
    )

# Anti « DNS rebinding » : un site malveillant ouvert dans un autre onglet
# peut faire pointer son domaine vers 127.0.0.1 et interroger ce serveur
# depuis le navigateur. On rejette toute requête dont l'en-tête Host n'est
# pas explicitement la machine locale.
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"]
)

# Anti-CSRF. Une page tierce ouverte dans un autre onglet peut émettre vers
# 127.0.0.1 des requêtes dites « simples » (POST en text/plain ou multipart) :
# elles ne déclenchent pas de contrôle préalable du navigateur, et la session
# étant ici un état du serveur — pas un cookie — elles arrivent authentifiées.
# La réponse reste illisible pour la page tierce (aucun en-tête CORS émis) :
# le risque n'est pas l'exfiltration mais la destruction (une boucle sur
# POST /api/sauvegarde remplaçait tout l'historique par dix copies de l'état
# courant). On refuse donc toute requête modifiante dont l'origine déclarée
# n'est pas la machine locale. Les clients hors navigateur (tests, scripts)
# n'envoient ni Origin ni Referer : ils restent acceptés.
METHODES_MODIFIANTES = frozenset({"POST", "PUT", "PATCH", "DELETE"})
HOTES_LOCAUX = frozenset({"127.0.0.1", "localhost", "::1"})


def origine_locale(valeur: str) -> bool:
    """Vrai si l'URL déclarée par le navigateur désigne bien cette machine."""
    try:
        u = urlparse(valeur)
    except ValueError:  # en-tête malformé
        return False
    return u.scheme in ("http", "https") and (u.hostname or "") in HOTES_LOCAUX


class AntiCSRF:
    """Middleware ASGI « pur », volontairement pas un `@app.middleware("http")`
    (BaseHTTPMiddleware) : celui-ci s'interpose sur le canal de réception et
    masque la fermeture de la requête par le navigateur à
    `request.is_disconnected()`. L'abandon d'analyse (bouton « Annuler »,
    `_jusqu_au_depart_du_client`) ne voyait alors jamais le départ du
    navigateur : l'analyse « annulée » continuait jusqu'au bout, gardait sa
    place (409 « déjà en cours » à la relance) et persistait son résultat."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in METHODES_MODIFIANTES:
            en_tetes = Headers(scope=scope)
            declaree = en_tetes.get("origin") or en_tetes.get("referer")
            if declaree and not origine_locale(declaree):
                logger.warning("Requête modifiante refusée (origine %s)", declaree)
                refus = JSONResponse(
                    status_code=403,
                    content={"detail": "Requête refusée : elle provient d'une page "
                                       "externe. Utilisez l'application depuis sa "
                                       "propre fenêtre."},
                )
                await refus(scope, receive, send)
                return
        await self.app(scope, receive, send)


app.add_middleware(AntiCSRF)

# La passphrase est l'unique rempart du chiffrement du coffre : longueur
# minimale exigée à la création (les coffres existants restent ouvrables).
PASSPHRASE_MIN = 12


def require_unlock() -> None:
    """Dépendance : exige une session déverrouillée, applique l'auto-verrouillage."""
    if security.enforce_inactivity() or not security.is_unlocked():
        raise HTTPException(423, "Application verrouillée.")
    security.touch()


# --- Session / sécurité ------------------------------------------------------

@app.get("/api/status")
async def status() -> StatusResponse:
    exists = security.db_exists()
    return StatusResponse(
        db_exists=exists, unlocked=security.is_unlocked(), first_run=not exists,
        version=__version__,
    )


def _refuser_passphrase_faible(p: str) -> None:
    """Politique commune à la création du coffre et au changement de passphrase
    (les coffres existants restent ouvrables tels quels)."""
    if len(p) < PASSPHRASE_MIN:
        raise HTTPException(
            400,
            f"Passphrase trop courte : {PASSPHRASE_MIN} caractères minimum "
            "pour protéger le coffre.",
        )
    raison = security.passphrase_faible(p)
    if raison:
        raise HTTPException(
            400,
            f"Passphrase {raison} : préférez une phrase de plusieurs mots. Une copie "
            "de votre coffre (clé USB perdue) peut être attaquée hors ligne, sans "
            "limite d'essais.",
        )


@app.post("/api/unlock")
async def unlock(req: UnlockRequest) -> OkResponse:
    if not req.passphrase.strip():
        raise HTTPException(400, "Passphrase vide.")
    if not security.db_exists():
        _refuser_passphrase_faible(req.passphrase)
    # Threadpool : dérivation de clé + purge + sauvegarde auto (VACUUM INTO)
    # peuvent prendre plusieurs secondes sur une grosse base — l'event loop
    # (keepalive, dictée) doit rester réactif.
    if await run_in_threadpool(security.unlock, req.passphrase):
        return OkResponse(ok=True)
    raise HTTPException(401, "Passphrase incorrecte.")


@app.post("/api/lock")
async def lock() -> OkResponse:
    security.lock()
    return OkResponse(ok=True)


@app.post("/api/keepalive", dependencies=[Depends(require_unlock)])
async def keepalive() -> OkResponse:
    """Rafraîchit le minuteur d'inactivité (ping émis pendant une dictée en
    cours : l'enregistrement audio est côté navigateur et ne touche pas le
    serveur, sans quoi le coffre s'auto-verrouille et la transcription échoue)."""
    return OkResponse(ok=True)


# --- Premier lancement guidé (avant même la création du coffre) --------------

def _cfg_courante() -> dict:
    """Config effective si déverrouillé, défauts sinon (aucune donnée patient)."""
    if security.is_unlocked():
        with security.transaction() as con:
            return config.ConfigStore(con).effective()
    # Copie : renvoyer DEFAULTS lui-même exposerait le dict global mutable.
    return copy.deepcopy(config.DEFAULTS)


@app.get("/api/installation")
async def etat_installation(modele: str = "") -> dict:
    """``modele`` : modèle de remplacement choisi à l'écran d'installation
    quand la proposition n'a pas pu être téléchargée."""
    etat = await run_in_threadpool(systeme.etat_installation, _cfg_courante(), modele)
    # Coffre verrouillé : la config lue est celle des *défauts*, pas celle du
    # praticien — le modèle « manquant » annoncé serait alors faux (et redemandé
    # à chaque lancement). L'interface a besoin de le savoir pour ne rien
    # affirmer qu'elle ne puisse vérifier.
    etat["config_lisible"] = security.is_unlocked()
    return etat


@app.post("/api/installation/pull")
async def pull_modele(req: dict) -> StreamingResponse:
    """Télécharge un modèle Ollama en relayant la progression (NDJSON)."""
    nom = (req or {}).get("modele", "")
    if not systeme.nom_modele_valide(nom):
        raise HTTPException(400, "Nom de modèle invalide.")
    if systeme.nom_modele_cloud(nom):
        raise HTTPException(
            400,
            f"« {nom} » est un modèle hébergé par Ollama sur Internet : il est "
            "refusé, les données patient ne quittent pas la machine.",
        )
    host = _cfg_courante()["llm"].get("host") or "http://localhost:11434"

    async def relais():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", f"{host}/api/pull", json={"model": nom}
                ) as resp:
                    async for ligne in resp.aiter_lines():
                        if ligne.strip():
                            yield ligne + "\n"
        except httpx.HTTPError:
            yield '{"error": "Ollama injoignable."}\n'

    return StreamingResponse(relais(), media_type="application/x-ndjson")


@app.post("/api/installation/whisper")
async def telecharger_whisper() -> dict:
    """Lance le téléchargement du modèle de dictée en arrière-plan ; l'état
    se suit via GET /api/installation (whisper_telechargement)."""
    return await run_in_threadpool(stt.telecharger_en_arriere_plan, _cfg_courante())


# --- Configuration -----------------------------------------------------------

@app.get("/api/config", dependencies=[Depends(require_unlock)])
async def get_config() -> dict:
    with security.transaction() as con:
        return config.ConfigStore(con).effective()


@app.put("/api/config", dependencies=[Depends(require_unlock)])
async def put_config(patch: ConfigPatch) -> dict:
    overrides = patch.overrides.model_dump(exclude_unset=True)
    with security.transaction() as con:
        return config.ConfigStore(con).set_overrides(overrides)


@app.delete("/api/config", dependencies=[Depends(require_unlock)])
async def reset_config() -> dict:
    """Réinitialise la configuration aux valeurs par défaut (efface les surcharges)."""
    with security.transaction() as con:
        eff = config.ConfigStore(con).reset()
        security.audit("config_reset", "config", None, "")
        return eff


@app.get("/api/config/overrides", dependencies=[Depends(require_unlock)])
async def get_config_overrides() -> dict:
    """Surcharges praticien seules (sans les défauts) — les éditeurs dédiés
    s'en servent pour indiquer la provenance des réglages (intégré/personnalisé)."""
    with security.transaction() as con:
        return config.ConfigStore(con).overrides()


@app.get("/api/domaines")
async def get_domaines() -> list[dict]:
    return config.DOMAINES


# --- Mise à jour de l'application ---------------------------------------------

@app.get("/api/maj")
async def verifier_maj(auto: bool = False) -> MajResponse:
    """Compare la version en cours à la dernière release GitHub publiée.

    Pas de dépendance au coffre (aucune donnée patient) : comme /api/status,
    la route répond même verrouillée. ``auto=1`` (vérification du démarrage)
    respecte la cadence d'une fois par jour et la version ignorée, en
    s'appuyant sur l'état local — donc seulement coffre déverrouillé ; le
    bouton « Vérifier maintenant » interroge toujours GitHub."""
    etat: dict = {}
    if security.is_unlocked():
        with security.transaction() as con:
            etat = maj.etat_lire(con)
    if auto and etat and not maj.doit_verifier(etat) and isinstance(etat.get("resultat"), dict):
        return MajResponse(**maj.appliquer_etat(etat["resultat"], etat))
    try:
        resultat = await maj.verifier()
    except maj.MajIndisponible as e:
        raise HTTPException(503, str(e))
    if security.is_unlocked():
        with security.transaction() as con:
            etat = maj.etat_ecrire(con, derniere=resultat["verifiee_le"], resultat=resultat)
    return MajResponse(**maj.appliquer_etat(resultat, etat))


@app.get("/api/maj/etat", dependencies=[Depends(require_unlock)])
async def lire_etat_maj() -> dict:
    """État local des mises à jour : information affichée, version ignorée,
    date de la dernière vérification."""
    with security.transaction() as con:
        etat = maj.etat_lire(con)
    return {
        "info_vue": bool(etat.get("info_vue")),
        "ignoree": etat.get("ignoree") or "",
        "derniere": etat.get("derniere") or "",
    }


@app.put("/api/maj/etat", dependencies=[Depends(require_unlock)])
async def modifier_etat_maj(corps: MajEtatPatch) -> dict:
    champs: dict = {}
    if corps.info_vue is not None:
        champs["info_vue"] = corps.info_vue
    if corps.ignoree is not None:
        champs["ignoree"] = corps.ignoree.strip() or None
    with security.transaction() as con:
        etat = maj.etat_ecrire(con, **champs)
    return {
        "info_vue": bool(etat.get("info_vue")),
        "ignoree": etat.get("ignoree") or "",
        "derniere": etat.get("derniere") or "",
    }


@app.post("/api/maj/telecharger", dependencies=[Depends(require_unlock)])
async def telecharger_maj(corps: MajTelechargement) -> StreamingResponse:
    """Télécharge l'installeur d'une version et le vérifie (signature des
    empreintes, puis empreinte du fichier) en relayant la progression (NDJSON).
    Réservé à l'application Windows installée : ailleurs, le fichier ne
    servirait à rien."""
    if not maj.installation_possible():
        raise HTTPException(400, maj.MSG_INSTALLATION_IMPOSSIBLE)
    try:
        maj.url_asset(corps.version, maj.NOM_SOMMES)
    except maj.MajRefusee as e:
        raise HTTPException(400, str(e))

    async def relais():
        async for evt in maj.telecharger(corps.version):
            yield json.dumps(evt, ensure_ascii=False) + "\n"

    return StreamingResponse(relais(), media_type="application/x-ndjson")


@app.post("/api/maj/installer", dependencies=[Depends(require_unlock)])
async def installer_maj(corps: MajInstallation) -> dict:
    """Sauvegarde le coffre puis lance l'installeur vérifié, qui ferme et
    relance l'application. La réponse part avant la fermeture."""
    if not maj.installation_possible():
        raise HTTPException(400, maj.MSG_INSTALLATION_IMPOSSIBLE)
    try:
        chemin = await run_in_threadpool(maj.fichier_verifie, corps.version)
    except maj.MajRefusee as e:
        raise HTTPException(409, str(e))

    def _sauvegarder() -> dict:
        with security.transaction() as con:
            cfg = config.ConfigStore(con).effective()
            res = sauvegarde.creer(con, cfg)
            security.audit("maj_installation", "app", None, f"v{corps.version}")
            return res

    try:
        sauv = await run_in_threadpool(_sauvegarder)
    except Exception:
        logger.exception("Sauvegarde avant mise à jour impossible")
        raise HTTPException(
            500,
            "La sauvegarde du coffre a échoué : la mise à jour n'a pas été lancée. "
            "Vérifiez le dossier de sauvegarde (⚙️ Paramètres) puis réessayez.",
        )
    try:
        maj.lancer_installeur(chemin, corps.port)
    except OSError as e:
        logger.exception("Lancement de l'installeur impossible")
        raise HTTPException(500, f"Impossible de lancer l'installeur : {e}")
    return {"lance": True, "sauvegarde": sauv.get("fichier", ""), "version": corps.version}


# Routes des éditeurs dédiés (Paramètres) : remplacement EN BLOC d'une section.
# Le PUT /api/config fusionne en profondeur et ne sait donc ni retirer une
# rubrique de trame, ni supprimer un domaine surchargé, ni effacer un prompt.

@app.put("/api/config/trame", dependencies=[Depends(require_unlock)])
async def put_config_trame(corps: TrameRemplacement) -> dict:
    with security.transaction() as con:
        eff = config.ConfigStore(con).remplacer_section("trame", corps.model_dump())
        security.audit("config_trame", "config", None, "remplacement")
        return eff


@app.post("/api/config/trame/analyse", dependencies=[Depends(require_unlock)])
async def analyser_trame(fichier: UploadFile = File(...)) -> dict:
    """Trame proposée d'après les intitulés d'un bilan du praticien (lot C).

    Le document est lu, jamais conservé ni indexé ; rien n'est enregistré :
    la proposition remplace la liste en édition de l'écran Paramètres, que le
    praticien vérifie avant « Enregistrer la trame ». Le nom du fichier n'est
    pas journalisé (il porte souvent l'identité du patient)."""
    data = await _lire_borne(fichier, TAILLE_MAX_DOCUMENT, "Document")
    if not data:
        raise HTTPException(400, "Fichier vide.")
    try:
        lignes = await run_in_threadpool(importer.extraire_lignes, data, fichier.filename or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    proposition = importer.proposer_trame_lignes(lignes)
    if not proposition:
        raise HTTPException(
            422,
            "Moins de deux rubriques repérées dans ce document. La reprise de trame "
            "s'appuie sur les titres (styles Word ou LibreOffice), les lignes en gras "
            "ou les intitulés courts seuls sur leur ligne.",
        )
    with security.transaction():
        security.audit(
            "config_trame", "config", None,
            f"analyse · {_type_fichier(fichier.filename)} · "
            f"{len(proposition['sections'])} rubriques",
        )
    return proposition


@app.delete("/api/config/trame", dependencies=[Depends(require_unlock)])
async def delete_config_trame() -> dict:
    """Retour à la trame réglementaire (les défauts suivent les mises à jour)."""
    with security.transaction() as con:
        eff = config.ConfigStore(con).effacer_section("trame")
        security.audit("config_trame", "config", None, "réinitialisation")
        return eff


@app.put("/api/config/catalogues", dependencies=[Depends(require_unlock)])
async def put_config_catalogues(corps: dict[str, CatalogueDomaine]) -> dict:
    """Remplace l'ensemble des surcharges de catalogues. Un domaine absent du
    corps redevient intégré ; {} = plus aucune surcharge."""
    connus = {d["cle"] for d in config.DOMAINES}
    inconnus = sorted(set(corps) - connus)
    if inconnus:
        raise HTTPException(422, f"Domaine inconnu : {', '.join(inconnus)}.")
    with security.transaction() as con:
        store = config.ConfigStore(con)
        if corps:
            eff = store.remplacer_section(
                "catalogues",
                {cle: dom.model_dump(exclude_none=True) for cle, dom in corps.items()},
            )
        else:
            eff = store.effacer_section("catalogues")
        security.audit(
            "config_catalogues", "config", None,
            "remplacement" if corps else "réinitialisation",
        )
        return eff


@app.delete("/api/config/catalogues", dependencies=[Depends(require_unlock)])
async def delete_config_catalogues() -> dict:
    with security.transaction() as con:
        eff = config.ConfigStore(con).effacer_section("catalogues")
        security.audit("config_catalogues", "config", None, "réinitialisation")
        return eff


@app.put("/api/config/prompts", dependencies=[Depends(require_unlock)])
async def put_config_prompts(corps: PromptRemplacement) -> dict:
    """Un prompt vide = retour à la consigne intégrée : on ne fige jamais une
    surcharge vide (elle masquerait les mises à jour de l'application)."""
    with security.transaction() as con:
        store = config.ConfigStore(con)
        if corps.structure_system.strip():
            eff = store.remplacer_section(
                "prompts", {"structure_system": corps.structure_system}
            )
            details = "remplacement"
        else:
            eff = store.effacer_section("prompts")
            details = "réinitialisation"
        security.audit("config_prompts", "config", None, details)
        return eff


@app.delete("/api/config/prompts", dependencies=[Depends(require_unlock)])
async def delete_config_prompts() -> dict:
    with security.transaction() as con:
        eff = config.ConfigStore(con).effacer_section("prompts")
        security.audit("config_prompts", "config", None, "réinitialisation")
        return eff


# --- Mise en page des exports (lot B du plan « mise en forme ») ------------

@app.put("/api/config/logo", dependencies=[Depends(require_unlock)])
async def put_logo(fichier: UploadFile = File(...)) -> dict:
    """Logo du cabinet pour l'en-tête des exports : PNG ou JPEG vérifié avec
    Pillow (pas seulement l'extension), réduit à 400 px de haut et rangé en
    base64 dans la configuration chiffrée — jamais en fichier à côté du
    coffre. Retourne la configuration effective."""
    data = await _lire_borne(fichier, export.TAILLE_MAX_LOGO, "Logo")
    try:
        logo = await run_in_threadpool(export.preparer_logo, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with security.transaction() as con:
        eff = config.ConfigStore(con).set_overrides({"mise_en_page": {"logo": logo}})
        security.audit("config_logo", "config", None, "dépôt")
        return eff


@app.delete("/api/config/logo", dependencies=[Depends(require_unlock)])
async def delete_logo() -> dict:
    """Retire le logo sans toucher aux autres réglages de mise en page."""
    with security.transaction() as con:
        eff = config.ConfigStore(con).effacer_cles("mise_en_page", ["logo"])
        security.audit("config_logo", "config", None, "retrait")
        return eff


# --- Gabarit Word du cabinet (lot D du plan « mise en forme ») ---------------

_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@app.put("/api/config/gabarit", dependencies=[Depends(require_unlock)])
async def put_gabarit(fichier: UploadFile = File(...)) -> dict:
    """Gabarit Word (.docx ; un modèle .dotx est converti) dont les exports
    Word reprennent l'en-tête, le pied de page, les sections et les styles.
    Vérifié (enveloppe Word, pas de macro, mise en page d'un bilan d'essai)
    puis rangé dans le coffre chiffré, à part de la configuration. Retourne
    la configuration effective, description du gabarit comprise."""
    data = await _lire_borne(fichier, export.TAILLE_MAX_GABARIT, "Gabarit")
    try:
        data, description = await run_in_threadpool(
            export.preparer_gabarit, data, fichier.filename or ""
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with security.transaction() as con:
        eff = config.ConfigStore(con).set_gabarit_docx(data, description)
        security.audit("config_gabarit", "config", None, "dépôt")
        return eff


@app.get("/api/config/gabarit", dependencies=[Depends(require_unlock)])
async def get_gabarit():
    """Le gabarit tel qu'il est conservé (.docx), pour le récupérer ou le
    retoucher dans Word."""
    with security.transaction() as con:
        store = config.ConfigStore(con)
        data = store.gabarit_docx()
        description = store.effective()["mise_en_page"].get("gabarit") or {}
    if not data:
        raise HTTPException(404, "Aucun gabarit déposé.")
    nom = description.get("nom") or "gabarit.docx"
    return Response(
        content=data, media_type=_MIME_DOCX,
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@app.delete("/api/config/gabarit", dependencies=[Depends(require_unlock)])
async def delete_gabarit() -> dict:
    """Retire le gabarit (description et fichier) sans toucher aux autres
    réglages de mise en page."""
    with security.transaction() as con:
        eff = config.ConfigStore(con).effacer_gabarit_docx()
        security.audit("config_gabarit", "config", None, "retrait")
        return eff


@app.post("/api/config/mise_en_page/apercu", dependencies=[Depends(require_unlock)])
async def apercu_mise_en_page(
    reglages: MiseEnPagePatch, format: Literal["pdf", "docx"] = "pdf",
):
    """Bilan fictif mis en page avec les réglages envoyés (ceux de l'écran,
    pas encore enregistrés) par-dessus la configuration en place (logo et
    gabarit compris) : l'écran Paramètres montre l'effet avant d'enregistrer.
    PDF affiché dans le cadre ; `format=docx` rend le Word (sur le gabarit
    s'il y en a un) à ouvrir dans Word."""
    with security.transaction() as con:
        store = config.ConfigStore(con)
        cfg = store.effective()
        gabarit = store.gabarit_docx() if format == "docx" else None
    cfg["mise_en_page"] = config._deep_merge(
        cfg["mise_en_page"], reglages.model_dump(exclude_unset=True)
    )
    exemple = export.bilan_exemple(cfg)
    try:
        if format == "docx":
            data = await run_in_threadpool(export.to_docx, exemple, cfg, gabarit)
        else:
            data = await run_in_threadpool(export.to_pdf, exemple, cfg)
    except Exception:
        logger.exception("Échec de l'aperçu de mise en page (%s)", format)
        raise HTTPException(500, "L'aperçu n'a pas pu être mis en page avec ces réglages.")
    if format == "docx":
        return Response(
            content=data, media_type=_MIME_DOCX,
            headers={"Content-Disposition": 'attachment; filename="exemple-mise-en-page.docx"'},
        )
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="apercu-mise-en-page.pdf"'},
    )


@app.get("/api/config/defauts", dependencies=[Depends(require_unlock)])
async def get_config_defauts() -> dict:
    """Valeurs par défaut seules. L'écran Paramètres affiche la valeur
    recommandée dans chaque bulle d'aide et signale les réglages qui s'en
    écartent — lues ici, jamais recopiées à la main (elles se périmeraient)."""
    return copy.deepcopy(config.DEFAULTS)


# Sections qu'un bouton « Revenir aux valeurs recommandées » peut effacer.
# Jamais `praticien` (une identité n'a pas de valeur recommandée) ; trame,
# catalogues et prompts ont leurs routes propres, déclarées avant celle-ci.
SECTIONS_REINITIALISABLES = frozenset({
    "llm", "stt", "embeddings", "style", "seuils", "cotation", "rgpd", "sauvegarde", "maj",
    "mise_en_page",
})


@app.delete("/api/config/{section}", dependencies=[Depends(require_unlock)])
async def delete_config_section(section: str, cles: str | None = None) -> dict:
    """Retour aux défauts d'une section, ou de quelques-unes de ses clés
    (`?cles=a,b`), sans toucher au reste : le « tout rétablir » global
    emportait vocabulaire, seuils, cotation et identité pour annuler l'essai
    d'un seul réglage."""
    if section not in SECTIONS_REINITIALISABLES:
        raise HTTPException(404, f"Section inconnue ou non réinitialisable : {section}.")
    liste = [c.strip() for c in (cles or "").split(",") if c.strip()]
    with security.transaction() as con:
        store = config.ConfigStore(con)
        eff = store.effacer_cles(section, liste) if liste else store.effacer_section(section)
        security.audit(
            "config_section", "config", None,
            section + (f":{','.join(liste)}" if liste else ""),
        )
        return eff


@app.get("/api/prompts/structure-defaut", dependencies=[Depends(require_unlock)])
async def prompt_structure_defaut() -> dict:
    """Consigne de structuration intégrée, prête à personnaliser.

    STRUCTURE_SYSTEM est un gabarit ``.format`` : ses accolades JSON sont
    doublées (``{{…}}``). Un prompt personnalisé est appliqué par
    ``.replace("{cles}", …)`` — accolades simples. On dé-double donc ici (en
    laissant ``{cles}`` intact) pour que ce texte, enregistré tel quel, soit
    strictement équivalent à la consigne intégrée."""
    return {"prompt": prompts.STRUCTURE_SYSTEM.replace("{{", "{").replace("}}", "}")}


# --- Bornes des corps envoyés ------------------------------------------------
# Les deux routes d'envoi de fichier lisaient tout le corps en mémoire sans
# plafond (revue 2026-08-11, 5.5). Un enregistrement WAV 16 kHz mono pèse
# ~2 Mo/min : 30 minutes de dictée (défaut de `rgpd.dictee_max_minutes`)
# tiennent largement sous 100 Mo. Un compte-rendu scanné en PDF dépasse
# rarement quelques dizaines de Mo.
TAILLE_MAX_AUDIO = 100 * 1024 * 1024
TAILLE_MAX_DOCUMENT = 50 * 1024 * 1024
_BLOC_LECTURE = 1024 * 1024


async def _lire_borne(upload: UploadFile, max_octets: int, quoi: str) -> bytes:
    """Lit un fichier envoyé par blocs et refuse (413) au-delà de `max_octets`,
    sans jamais garder en mémoire plus que le plafond."""
    morceaux: list[bytes] = []
    total = 0
    while True:
        bloc = await upload.read(_BLOC_LECTURE)
        if not bloc:
            break
        total += len(bloc)
        if total > max_octets:
            raise HTTPException(
                413,
                f"{quoi} trop volumineux (plus de {max_octets // (1024 * 1024)} Mo).",
            )
        morceaux.append(bloc)
    return b"".join(morceaux)


# --- Abandon d'une analyse par le navigateur ---------------------------------
# Fréquence à laquelle on regarde si le navigateur a fermé la requête pendant
# que le modèle travaille.
_PAS_SURVEILLANCE_S = 0.5


class AnalyseAbandonnee(Exception):
    """Le navigateur a fermé la requête (bouton « Annuler », onglet fermé)."""


async def _jusqu_au_depart_du_client(request: Request, coro):
    """Exécute `coro` en surveillant la connexion du navigateur.

    S'il ferme la requête (« Annuler », onglet fermé), la tâche est annulée —
    ce qui coupe aussi l'appel HTTP vers Ollama, qui cesse alors de générer —
    et rien n'est écrit en base. Sans cela, une analyse « annulée » à l'écran
    continuait jusqu'à dix minutes côté serveur, puis persistait son résultat
    dans le bilan, éventuellement par-dessus une nouvelle dictée."""
    tache = asyncio.ensure_future(coro)
    try:
        while True:
            fini, _ = await asyncio.wait({tache}, timeout=_PAS_SURVEILLANCE_S)
            if fini:
                return tache.result()
            if await request.is_disconnected():
                tache.cancel()
                # `wait` (et non `await tache`) : on attend la fin de la tâche
                # sans relever son CancelledError.
                await asyncio.wait({tache})
                raise AnalyseAbandonnee()
    except asyncio.CancelledError:
        tache.cancel()
        raise


# --- Dictée vocale locale ----------------------------------------------------

@app.get("/api/stt/info", dependencies=[Depends(require_unlock)])
async def stt_info() -> dict:
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
    return stt.resolved(cfg)


@app.post("/api/transcribe", dependencies=[Depends(require_unlock)])
async def transcribe(audio: UploadFile = File(...)) -> dict:
    data = await _lire_borne(audio, TAILLE_MAX_AUDIO, "Enregistrement audio")
    if not data:
        raise HTTPException(400, "Audio vide.")
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
    try:
        result = await run_in_threadpool(stt.transcribe, data, audio.filename or "", cfg)
    except stt.STTUnavailable as exc:
        raise HTTPException(503, str(exc))
    except stt.AudioIllisible as exc:
        logger.warning("Audio de dictée illisible : %s", exc)
        raise HTTPException(
            400,
            "Enregistrement audio illisible (fichier tronqué ou format non "
            "reconnu). Réenregistrez votre dictée.",
        )
    except Exception as exc:
        # Jamais la trace technique (HuggingFace, ffmpeg…) dans l'interface :
        # elle part dans le journal, l'UI reçoit un message simple.
        logger.exception("Échec de la transcription : %s", exc)
        raise HTTPException(
            500,
            "La transcription a échoué. Réessayez ; au premier usage, le modèle "
            "de dictée doit d'abord finir de s'installer.",
        )
    with security.transaction() as con:
        # Journalise l'acte, jamais le contenu.
        security.audit("transcribe", "dictee", None, f"{len(result['text'])} car.")
    return result


# --- Patients -----------------------------------------------------------------

@app.get("/api/patients", dependencies=[Depends(require_unlock)])
async def list_patients() -> list[dict]:
    with security.transaction() as con:
        return patient.liste(con)


@app.post("/api/patients", dependencies=[Depends(require_unlock)])
async def create_patient(req: PatientIn) -> dict:
    if not req.nom.strip():
        raise HTTPException(400, "Nom requis.")
    with security.transaction() as con:
        pid = patient.create(con, req.nom, req.prenom, req.date_naissance, req.sexe, req.notes)
        security.audit("create", "patient", pid, "")
        return patient.get(con, pid)


@app.put("/api/patients/{patient_id}", dependencies=[Depends(require_unlock)])
async def update_patient(patient_id: int, req: PatientIn) -> dict:
    if not req.nom.strip():
        raise HTTPException(400, "Nom requis.")
    with security.transaction() as con:
        if not patient.update(con, patient_id, req.nom, req.prenom,
                              req.date_naissance, req.sexe, req.notes):
            raise HTTPException(404, "Patient introuvable.")
        security.audit("update", "patient", patient_id, "")
        return patient.get(con, patient_id)


@app.delete("/api/patients/{patient_id}", dependencies=[Depends(require_unlock)])
async def delete_patient(patient_id: int) -> OkResponse:
    """Effacement RGPD : supprime le patient et tous ses bilans (cascade)."""
    with security.transaction() as con:
        if not patient.delete(con, patient_id):
            raise HTTPException(404, "Patient introuvable.")
        security.audit("effacement_rgpd", "patient", patient_id, "bilans en cascade")
    return OkResponse(ok=True)


# --- Sauvegarde chiffrée du coffre --------------------------------------------

@app.post("/api/sauvegarde", dependencies=[Depends(require_unlock)])
async def creer_sauvegarde() -> dict:
    def _creer() -> dict:
        with security.transaction() as con:
            cfg = config.ConfigStore(con).effective()
            res = sauvegarde.creer(con, cfg)
            security.audit("sauvegarde", "app", None, f"{res['octets']} octets")
            return res

    # Threadpool : VACUUM INTO peut durer plusieurs secondes sur une grosse
    # base — le verrou est tenu dans un thread, l'event loop reste libre.
    # Limite assumée : pendant ce VACUUM, le verrou global bloque les AUTRES
    # requêtes à la base (gel borné et rare). L'alternative — une connexion
    # SQLCipher dédiée hors verrou — exigerait de conserver la clé en clair
    # hors de security._state : compromis de sécurité refusé.
    try:
        return await run_in_threadpool(_creer)
    except (security.CoffreVerrouille, sauvegarde.SupportIntrouvable):
        raise  # gérés globalement (423 / 400)
    except (sqlite3.OperationalError, sqlcipher3.OperationalError):
        raise  # géré globalement en 503 (disque plein ?)
    except Exception as exc:
        raise HTTPException(500, f"Échec de la sauvegarde : {exc}")


@app.get("/api/sauvegardes", dependencies=[Depends(require_unlock)])
async def list_sauvegardes() -> dict:
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
        return sauvegarde.liste(con, cfg)


# Une seule restauration à la fois : sans cette garde, la seconde requête
# gèlerait sur le verrou global puis restaurerait par-dessus le résultat de
# la première. Même esprit que la garde des analyses (_analyses_en_cours).
_restauration_verrou = threading.Lock()


@app.post("/api/passphrase", dependencies=[Depends(require_unlock)])
async def changer_passphrase(req: PassphraseChange) -> dict:
    """Rotation de la passphrase du coffre : re-chiffrement sur place, puis
    nouvelle sauvegarde chiffrée avec la nouvelle clé."""
    if not req.ancienne.strip() or not req.nouvelle.strip():
        raise HTTPException(400, "Passphrase vide.")
    if req.nouvelle == req.ancienne:
        raise HTTPException(400, "La nouvelle passphrase est identique à l'actuelle.")
    _refuser_passphrase_faible(req.nouvelle)
    try:
        # Threadpool : le re-chiffrement réécrit chaque page, puis VACUUM INTO.
        res = await run_in_threadpool(security.changer_passphrase, req.ancienne, req.nouvelle)
    except security.PassphraseIncorrecte as exc:
        raise HTTPException(401, str(exc))
    return res


@app.post("/api/restauration", dependencies=[Depends(require_unlock)])
async def restaurer_sauvegarde(req: RestaurationRequest) -> dict:
    """Restauration guidée : vérifie que la copie s'ouvre avec la passphrase,
    sauvegarde la base actuelle en filet, échange les fichiers atomiquement
    puis rouvre le coffre."""
    if not req.passphrase.strip():
        raise HTTPException(400, "Passphrase vide.")
    if not _restauration_verrou.acquire(blocking=False):
        raise HTTPException(
            409, "Une restauration est déjà en cours. Patientez quelques instants."
        )
    try:
        # Threadpool : copie + vérification + VACUUM filet peuvent durer
        # plusieurs secondes — l'event loop doit rester réactif.
        return await run_in_threadpool(security.restaurer, req.fichier, req.passphrase)
    except security.RestaurationImpossible as exc:
        # Demande invalide (fichier, passphrase, version) : base intacte.
        raise HTTPException(400, str(exc))
    except (security.CoffreVerrouille, sauvegarde.SupportIntrouvable):
        raise  # gérés globalement (423 / 400)
    except (sqlite3.OperationalError, sqlcipher3.OperationalError):
        raise  # géré globalement en 503 (disque plein ?)
    except RuntimeError as exc:
        # Échec après le point de non-retour : message d'état précis
        # (« données intactes » ou « restaurée mais verrouillée »).
        raise HTTPException(500, str(exc))
    except Exception:
        logger.exception("Restauration : échec inattendu")
        raise HTTPException(500, "La restauration a échoué. Réessayez.")
    finally:
        _restauration_verrou.release()


# --- Bilans & structuration IA ----------------------------------------------

@app.post("/api/bilans", dependencies=[Depends(require_unlock)])
async def create_bilan(req: BilanCreate) -> dict:
    with security.transaction() as con:
        if req.patient_id is not None and not patient.get(con, req.patient_id):
            raise HTTPException(404, "Patient introuvable.")
        cfg = config.ConfigStore(con).effective()
        bid = bilan.create(
            con, req.domaines, req.type.value, req.patient_id, req.motif, cfg,
            date_bilan=req.date_bilan,
            prescripteur=req.prescripteur,
            prescripteur_rpps=req.prescripteur_rpps,
        )
        security.audit("create", "bilan", bid, "")
        return bilan.get(con, bid)


@app.put("/api/bilans/{bilan_id}", dependencies=[Depends(require_unlock)])
async def patch_bilan(bilan_id: int, req: BilanPatch) -> dict:
    """En-tête du bilan : date et prescripteur. Tous deux figurent sur le
    document adressé au médecin et doivent rester corrigeables après coup."""
    with security.transaction() as con:
        if not bilan.maj_entete(
            con, bilan_id,
            date_bilan=req.date_bilan,
            prescripteur=req.prescripteur,
            prescripteur_rpps=req.prescripteur_rpps,
        ):
            raise HTTPException(404, "Bilan introuvable.")
        security.audit("entete", "bilan", bilan_id, "")
        return bilan.get(con, bilan_id)


@app.get("/api/bilans", dependencies=[Depends(require_unlock)])
async def list_bilans(limit: int = 20, offset: int = 0) -> list[dict]:
    """Liste paginée : sans pagination, les bilans au-delà du plafond
    disparaissaient purement et simplement de l'interface (audit)."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    with security.transaction() as con:
        return bilan.liste(con, limit=limit, offset=offset)


@app.get("/api/bilans/{bilan_id}", dependencies=[Depends(require_unlock)])
async def get_bilan(bilan_id: int) -> dict:
    with security.transaction() as con:
        b = bilan.get(con, bilan_id)
    if not b:
        raise HTTPException(404, "Bilan introuvable.")
    return b


# Garde anti-concurrence : une seule analyse à la fois par bilan. Deux analyses
# simultanées appliqueraient chacune leur append (apply_updates) — contenu
# dupliqué. Le frontend a son propre anti-rebond, mais un second onglet ou un
# client direct de l'API n'en bénéficie pas.
_analyses_en_cours: set[int] = set()
_analyses_lock = threading.Lock()


@app.post("/api/bilans/{bilan_id}/structure", dependencies=[Depends(require_unlock)])
async def structure_bilan(bilan_id: int, req: StructureRequest, request: Request) -> dict:
    if not req.transcription.strip() and not req.reponses:
        raise HTTPException(400, "Rien à structurer : ni dictée, ni réponse.")
    with security.transaction() as con:
        b = bilan.get(con, bilan_id)
        cfg = config.ConfigStore(con).effective()
    if not b:
        raise HTTPException(404, "Bilan introuvable.")
    with _analyses_lock:
        if bilan_id in _analyses_en_cours:
            raise HTTPException(409, "Une analyse est déjà en cours pour ce bilan.")
        _analyses_en_cours.add(bilan_id)
    try:
        # Toute l'analyse est surveillée, pas seulement l'appel au modèle : le
        # calcul d'embedding qui le précède peut durer plusieurs secondes (carte
        # graphique partagée entre deux modèles), et un « Annuler » pendant ce
        # temps n'était vu qu'après — la place restait prise et la relance
        # recevait 409.
        return await _jusqu_au_depart_du_client(
            request, _structurer(bilan_id, req, b, cfg)
        )
    except AnalyseAbandonnee:
        # Personne n'écoute plus la réponse : on journalise l'abandon et on
        # sort sans rien écrire. 499 = « client closed request ».
        logger.info("Analyse du bilan %s abandonnée par le navigateur", bilan_id)
        raise HTTPException(499, "Analyse annulée.")
    finally:
        with _analyses_lock:
            _analyses_en_cours.discard(bilan_id)


async def _structurer(bilan_id: int, req: StructureRequest, b: dict, cfg: dict) -> dict:
    # Texte de ce tour (dictée + réponses) : sert à retrouver des extraits proches.
    texte_tour = " ".join(
        [req.transcription.strip()]
        + [f"{r.question} {r.reponse}" for r in req.reponses]
    ).strip()
    # Récupère des extraits du praticien pour inspirer le style (best-effort).
    # L'embedding (appel réseau) est calculé HORS du verrou : un Ollama lent
    # ne gèle plus le serveur (audit C3).
    #
    # Un échec ne bloque pas l'analyse, mais il n'est plus silencieux : le
    # style du praticien est l'argument central du produit, et le voir cesser
    # de s'appliquer sans un mot laissait croire à une IA qui « écrit moins
    # bien » sans cause visible.
    style, style_indisponible = [], ""
    dom = b["domaines"][0] if b["domaines"] else None
    k = cfg["style"]["few_shot_k"]
    a_des_refs = False
    if texte_tour and k:
        with security.transaction() as con:
            a_des_refs = rag.a_des_references(con)
    if a_des_refs:
        try:
            emb = await rag.embed(texte_tour, cfg)
            with security.transaction() as con:
                refs = rag.retrieve(con, emb, domaine=dom, k=k)
            style = [r["texte"][:800] for r in refs]
        except security.CoffreVerrouille:
            raise  # géré globalement en 423
        except rag.EmbeddingUnavailable as exc:
            logger.warning("Style du praticien non réinjecté : %s", exc)
            style_indisponible = str(exc)
        except Exception:
            logger.exception("Style du praticien non réinjecté (erreur inattendue)")
            style_indisponible = (
                "Vos bilans de référence n'ont pas pu être consultés pour ce passage."
            )
    # Données patient minimisées pour le LLM : âge (clé des étalonnages) et
    # sexe uniquement — jamais l'identité.
    patient_desc = ""
    p = b.get("patient") or {}
    if p.get("date_naissance"):
        age = patient.age_texte(p["date_naissance"], b.get("created_at"))
        if age:
            patient_desc = f"âge à la date du bilan : {age}"
    if p.get("sexe"):
        patient_desc += (", " if patient_desc else "") + f"sexe : {p['sexe']}"
    try:
        result = await llm.structure(
            req.transcription, b["sections"], b["domaines"], cfg,
            style_examples=style, patient_desc=patient_desc,
            reponses=[r.model_dump() for r in req.reponses],
            questions_en_attente=req.questions_en_attente,
            questions_ecartees=req.questions_ecartees,
            questions_repondues=req.questions_repondues,
        )
    except llm.ModeleIntrouvable as exc:
        raise HTTPException(
            503,
            f"Le modèle « {exc} » n'est pas téléchargé. Ouvrez ⚙️ Paramètres → "
            "Modèles pour le télécharger.",
        )
    except llm.ModeleCloud as exc:
        raise HTTPException(
            400,
            f"Le modèle « {exc} » est hébergé par Ollama sur Internet : il est "
            "refusé, les données patient ne quittent pas la machine. Choisissez "
            "un modèle local (⚙️ Paramètres).",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            504,
            "Le modèle n'a pas répondu dans le délai imparti. Réessayez, ou "
            "choisissez un modèle plus léger (⚙️ Paramètres).",
        )
    except httpx.HTTPError:
        raise HTTPException(
            503,
            "Le moteur d'IA local (Ollama) ne répond pas. Vérifiez qu'il est "
            "bien démarré, puis réessayez.",
        )
    except llm.ReponseIllisible as exc:
        raise HTTPException(502, str(exc))
    # Traçabilité des chiffres : tout nombre proposé doit se retrouver dans le
    # matériau source (dictée de ce tour, réponses, contenu déjà relu par le
    # praticien). Le modèle local transpose parfois un écart-type en percentile
    # ou attribue un résultat au mauvais test ; aucune consigne de prompt ne le
    # garantit. On ne corrige rien — on signale, le praticien tranche.
    sources = (
        [req.transcription]
        + [f"{r.question} {r.reponse}" for r in req.reponses]
        # Contenu déjà rédigé — mais SEULEMENT les rubriques qui ne portent plus
        # d'avertissement en attente. Sans cette restriction, un chiffre
        # halluciné au tour N (pas même encore relu) devenait une source
        # légitime au tour N+1 et cessait d'être signalé : le garde-fou
        # blanchissait sa propre alerte.
        + [
            s.get("contenu") or ""
            for s in b["sections"]
            if not s.get("signalements")
        ]
        # Les épreuves saisies à la main sont du matériau du praticien : un test
        # coté dans le tableau n'a pas à être signalé comme « non dicté ».
        + [e.get("test_nom") or "" for e in b.get("epreuves") or []]
    )
    # Noms de tests que le modèle a sous les yeux (prompt) — donc ceux qu'il
    # peut substituer. La vérification porte sur tous les domaines : le modèle
    # ne s'interdit pas de citer un test hors du domaine du bilan.
    noms_tests = catalogues.tous_les_noms(cfg)
    titres = {s["cle"]: s["titre"] for s in b["sections"]}
    rubriques_a_verifier = []
    # Le praticien a désactivé la mise en forme par l'IA : ce qu'elle a balisé
    # malgré la consigne est remis en clair ici, de façon déterministe.
    if not (cfg.get("style") or {}).get("mise_en_forme_ia", True):
        for u in result["updates"]:
            u["texte"] = texte_riche.en_clair(u["texte"])
    for u in result["updates"]:
        # Les vérificateurs lisent le texte sans marqueurs (« **-2,1 ET** »
        # reste un chiffre) et sans numéros de liste (qui ne sont pas des
        # valeurs cliniques à retrouver dans la dictée).
        clair = texte_riche.en_clair(u["texte"], numeroter=False)
        sources_claires = [texte_riche.en_clair(s, numeroter=False) for s in sources]
        msgs = (
            verif_chiffres.signalements(clair, sources_claires)
            # Un nom de test substitué ne portait jusqu'ici aucun signalement
            # exploitable : « chiffres absents : 6, -15 » pour « EVALEO 6-15 ».
            + verif_tests.signalements(clair, sources_claires, noms_tests)
            # Une prose entièrement inventée ne contient aucun chiffre : elle
            # passait sans un mot.
            + verif_texte.signalements(clair, sources_claires)
        )
        if msgs:
            rubriques_a_verifier.append({
                "section": u["section"],
                "titre": titres.get(u["section"], u["section"]),
                "signalements": msgs,
            })
    with security.transaction() as con:
        bilan.apply_updates(con, bilan_id, result["updates"])
        # Les avertissements suivent le texte qu'ils concernent, dans le coffre :
        # ils doivent survivre à un F5, à un verrouillage d'inactivité et à un
        # changement de dossier — c'est là qu'on revient relire « à valider ».
        # Complétés, jamais remplacés : le texte signalé au tour précédent est
        # toujours dans la rubrique (apply_updates concatène).
        for c in rubriques_a_verifier:
            bilan.ajouter_signalements(con, bilan_id, c["section"], c["signalements"])
        security.audit(
            "structure", "bilan", bilan_id,
            f"{len(result['updates'])} maj, {len(result['questions'])} questions"
            + (f", {len(req.reponses)} réponse(s) intégrée(s)" if req.reponses else "")
            + (f", {len(rubriques_a_verifier)} rubrique(s) à vérifier"
               if rubriques_a_verifier else ""),
        )
        b2 = bilan.get(con, bilan_id)
    return {
        "bilan": b2,
        "questions": result["questions"],
        # Rubriques trop longues, transmises seulement en partie au modèle :
        # l'interface le signale discrètement (l'anti-répétition en pâtit).
        "rubriques_tronquees": result.get("rubriques_tronquees", []),
        # Vide si le style a bien été réinjecté ; sinon, la cause à afficher.
        "style_indisponible": style_indisponible,
        # Ce que l'app n'a pas pu retrouver dans la dictée : chiffres, noms de
        # tests, ou rubrique entière trop peu adossée au matériau dicté.
        "rubriques_a_verifier": rubriques_a_verifier,
        # Rubriques rendues par le modèle sous un nom inconnu : le texte n'a pas
        # pu être placé. Signalé plutôt que perdu en silence.
        "updates_non_placees": result.get("updates_non_placees", []),
        # Le modèle s'est vraisemblablement arrêté en cours de route : le
        # praticien doit le savoir avant de relire un compte-rendu amputé.
        "analyse_incomplete": llm.couverture_suspecte(texte_tour, result["updates"]),
        # Le prompt approche la fenêtre de contexte : Ollama tronque alors le
        # DÉBUT du prompt, donc les consignes système, sans que rien ne le dise.
        "prompt_trop_long": result.get("prompt_trop_long", False),
    }


@app.put(
    "/api/bilans/{bilan_id}/sections/{cle}", dependencies=[Depends(require_unlock)]
)
async def put_section(bilan_id: int, cle: str, req: SectionPut) -> OkResponse:
    statut = req.statut.value if req.statut else None
    with security.transaction() as con:
        ok = bilan.update_section(con, bilan_id, cle, req.contenu, statut)
    if not ok:
        raise HTTPException(404, "Rubrique introuvable.")
    return OkResponse(ok=True)


@app.put("/api/bilans/{bilan_id}/statut", dependencies=[Depends(require_unlock)])
async def put_statut(bilan_id: int, req: StatutPut) -> dict:
    with security.transaction() as con:
        if not bilan.set_statut(con, bilan_id, req.statut.value, req.destinataire):
            raise HTTPException(404, "Bilan introuvable.")
        # Le nom du destinataire n'est pas journalisé : il reste dans la table
        # `envoi`, qui suit le bilan à la suppression — contrairement à
        # `audit_log`, qu'aucun effacement ne nettoie.
        security.audit(
            "statut", "bilan", bilan_id,
            req.statut.value + (" → destinataire enregistré" if req.destinataire else ""),
        )
        return bilan.get(con, bilan_id)


@app.get("/api/catalogues/{domaine}", dependencies=[Depends(require_unlock)])
async def get_catalogue(domaine: str) -> dict:
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
    return catalogues.get(domaine, cfg)


@app.post("/api/bilans/{bilan_id}/epreuves", dependencies=[Depends(require_unlock)])
async def add_epreuve(bilan_id: int, req: EpreuveCreate) -> dict:
    if not req.test_nom.strip():
        raise HTTPException(400, "Nom du test requis.")
    with security.transaction() as con:
        if not bilan.get(con, bilan_id):
            raise HTTPException(404, "Bilan introuvable.")
        cfg = config.ConfigStore(con).effective()
        # Les résultats vides sont écartés : un corps sans valeur exploitable
        # créait une ligne fantôme dans le tableau du compte-rendu.
        resultats = [r.model_dump() for r in req.resultats if r.exploitable()]
        bilan.add_epreuve(con, bilan_id, req.domaine, req.test_nom, req.version, resultats, cfg)
        security.audit("epreuve", "bilan", bilan_id, req.test_nom)
        b = bilan.get(con, bilan_id)
    # Contrôle de plausibilité de l'étalonnage saisi : on signale, on ne corrige
    # pas (le percentile -300 ou la note 85 sur l'échelle moy. 10 passaient sans
    # un mot, alors que le drapeau du compte-rendu en dépend).
    b["avertissements"] = bilan.alertes_plausibilite(req.test_nom, resultats)
    return b


@app.delete(
    "/api/bilans/{bilan_id}/epreuves/{epreuve_id}",
    dependencies=[Depends(require_unlock)],
)
async def del_epreuve(bilan_id: int, epreuve_id: int) -> dict:
    """Retire une épreuve mal saisie. Sans cette route, le seul recours était de
    supprimer le patient entier (cascade RGPD)."""
    with security.transaction() as con:
        if not bilan.delete_epreuve(con, bilan_id, epreuve_id):
            raise HTTPException(404, "Épreuve introuvable.")
        security.audit("suppression", "epreuve", epreuve_id, f"bilan {bilan_id}")
        return bilan.get(con, bilan_id)


@app.delete("/api/bilans/{bilan_id}", dependencies=[Depends(require_unlock)])
async def del_bilan(bilan_id: int) -> OkResponse:
    """Supprime un bilan et tout ce qui en dépend (rubriques, épreuves,
    résultats, cotation, envois, prescription)."""
    with security.transaction() as con:
        if not bilan.delete(con, bilan_id):
            raise HTTPException(404, "Bilan introuvable.")
        security.audit("suppression", "bilan", bilan_id, "")
    return OkResponse(ok=True)


@app.post("/api/bilans/{bilan_id}/cotation", dependencies=[Depends(require_unlock)])
async def cote_bilan(bilan_id: int) -> dict:
    with security.transaction() as con:
        b = bilan.get(con, bilan_id)
        if not b:
            raise HTTPException(404, "Bilan introuvable.")
        cfg = config.ConfigStore(con).effective()
        cot = cotation.compute(cfg, b.get("type", "initial_simple"))
        cotation.set_for_bilan(con, bilan_id, cot)
        security.audit("cotation", "bilan", bilan_id, cot["code_amo"])
    return cot


@app.get("/api/bilans/{bilan_id}/export", dependencies=[Depends(require_unlock)])
async def export_bilan(
    bilan_id: int, format: Literal["md", "txt", "docx", "pdf"] = "md",
):
    # `format` est contraint : « ?format=exe » renvoyait du Markdown en 200,
    # donc un fichier au mauvais nom et au mauvais contenu.
    # La config porte l'identité du praticien : sans elle, l'export ressortirait
    # sans en-tête ni signature, donc non envoyable en l'état.
    with security.transaction() as con:
        b = bilan.get(con, bilan_id)
        store = config.ConfigStore(con)
        cfg = store.effective()
        # Le gabarit Word du praticien ne sert qu'au Word : lu ici seulement.
        gabarit = store.gabarit_docx() if format == "docx" else None
    if not b:
        raise HTTPException(404, "Bilan introuvable.")
    fname = f"bilan-{bilan_id}"
    if format == "docx":
        try:
            data = export.to_docx(b, cfg, gabarit)
        except Exception:
            if not gabarit:
                raise
            # Un gabarit accepté a déjà mis en page un bilan d'essai ; s'il
            # échoue sur celui-ci, le praticien doit le savoir plutôt que
            # recevoir un document sans son papier à en-tête.
            logger.exception("Échec du Word sur le gabarit (bilan %s)", bilan_id)
            raise HTTPException(
                500,
                "Le gabarit Word n'a pas pu être appliqué à ce compte-rendu. "
                "Retirez-le dans Paramètres → Mise en page, ou exportez en PDF.",
            )
        return Response(
            content=data, media_type=_MIME_DOCX,
            headers={"Content-Disposition": f'attachment; filename="{fname}.docx"'},
        )
    if format == "pdf":
        # Seule mise en page qui puisse échouer sur le contenu lui-même : le
        # praticien doit récupérer un message exploitable, pas un 500 opaque au
        # moment d'envoyer le compte-rendu.
        try:
            contenu = export.to_pdf(b, cfg)
        except Exception:
            logger.exception("Échec de la mise en page PDF (bilan %s)", bilan_id)
            raise HTTPException(
                500,
                "La mise en page PDF a échoué sur ce compte-rendu. "
                "Exportez-le en Word (.docx) — le contenu y est identique.",
            )
        return Response(
            content=contenu,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'},
        )
    if format == "txt":
        return PlainTextResponse(
            export.to_txt(b, cfg),
            headers={"Content-Disposition": f'attachment; filename="{fname}.txt"'},
        )
    return PlainTextResponse(
        export.to_markdown(b, cfg),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}.md"'},
    )


# --- Base de bilans de référence (mémoire / style du praticien) -------------

def _type_fichier(nom: str | None) -> str:
    """Extension seule : le journal d'audit trace l'acte, jamais l'identité.

    « bilan-DUPONT-Jean-2024.pdf » inscrivait le nom du patient dans
    `audit_log`, table qu'aucune suppression ne nettoie."""
    suffixe = Path(nom or "").suffix.lower()
    return f"fichier {suffixe}" if suffixe else "fichier sans extension"

@app.post("/api/references", dependencies=[Depends(require_unlock)])
async def import_reference(
    file: UploadFile = File(...), domaine: str = Form(""),
    patient_id: int | None = Form(None),
) -> dict:
    data = await _lire_borne(file, TAILLE_MAX_DOCUMENT, "Document")
    if not data:
        raise HTTPException(400, "Fichier vide.")
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
    # 1. Extraction du texte (PDF/OCR : potentiellement plusieurs minutes)
    #    dans le threadpool — l'event loop reste réactif.
    try:
        lignes = await run_in_threadpool(importer.extraire_lignes, data, file.filename or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    chunks = importer.decouper_lignes(lignes)
    # 1 bis. Le bloc qui précède le premier en-tête d'un vrai compte-rendu est
    # son bloc d'identité (nom, naissance, adresse, prescripteur) — et il est
    # exempté du filtre de rubrique à la sélection, donc réinjectable dans
    # n'importe quel dossier. Le pack fictif l'écarte déjà : les imports du
    # praticien le doivent d'autant plus. Un document non sectionné (extrait
    # « global » unique) est conservé, sans quoi l'import ne donnerait rien.
    utiles = [c for c in chunks if c[0] != "global"] or chunks
    ecartes = len(chunks) - len(utiles)
    # 1 ter. Pseudonymisation : ces extraits sont destinés à être relus par le
    # modèle pendant la rédaction du bilan d'un AUTRE patient.
    caviardes = 0
    nettoyes = []
    # Les noms sont relevés sur le document ENTIER, en-tête compris : c'est lui
    # qui apprend que le prénom cité vingt lignes plus bas est celui du patient.
    noms = anonymisation.noms_du_document("\n".join(c[2] for c in chunks))
    for cle, titre, contenu in utiles:
        texte, n = anonymisation.caviarder(contenu, noms)
        caviardes += n
        nettoyes.append((cle, titre, texte))
    # 2. Embeddings (réseau) hors verrou : la dictée et le keepalive
    #    continuent de répondre pendant l'indexation.
    try:
        embs = [await rag.embed(contenu, cfg) for _, _, contenu in nettoyes]
    except rag.EmbeddingUnavailable as exc:
        raise HTTPException(503, str(exc))
    # 3. Insertion rapide sous verrou.
    with security.transaction() as con:
        if patient_id and not patient.get(con, patient_id):
            raise HTTPException(404, "Patient introuvable.")
        for (cle, titre, contenu), emb in zip(nettoyes, embs):
            rag.add_reference(
                con, None, "import", domaine, cle, titre, contenu, emb,
                patient_id=patient_id,
            )
        # Le nom du fichier est écarté du journal : « bilan-DUPONT-Jean.pdf »
        # inscrivait l'identité du patient dans une table qu'aucune suppression
        # ne nettoie.
        security.audit(
            "import_reference", "reference", None,
            f"{len(nettoyes)} extraits · {_type_fichier(file.filename)} · "
            f"{len(data) // 1024} Ko",
        )
    return {
        "n": len(nettoyes),
        "sections": [c[0] for c in nettoyes],
        "filename": file.filename or "",
        # Rendus à l'interface pour que le praticien sache ce qui a été fait de
        # son document, plutôt que de l'apprendre dans la documentation.
        "extraits_ecartes": ecartes,
        "elements_caviardes": caviardes,
        # Intitulés du document, dans l'ordre : l'interface propose d'en faire
        # la trame des prochains bilans (lot C). None si rien de net.
        "trame_proposee": importer.proposer_trame_lignes(lignes),
    }


@app.get("/api/references", dependencies=[Depends(require_unlock)])
async def list_references() -> list[dict]:
    with security.transaction() as con:
        return rag.liste(con)


def _decouper_pack(fichiers: list[tuple[str, str, bytes]]) -> list[tuple[str, str, str, str]]:
    """(domaine, clé de rubrique, titre, contenu) pour chaque extrait du pack.

    Les extraits « global » sont écartés : dans ces fichiers entièrement
    sectionnés, il ne reste avant le premier en-tête que la ligne-titre
    « DOCUMENT FICTIF » — du bruit, pas un extrait de style."""
    return [
        (domaine, cle, titre, contenu)
        for nom, domaine, data in fichiers
        for cle, titre, contenu in importer.decouper(data, nom)
        if cle != "global"
    ]


# Déclarées AVANT /api/references/{ref_id} : sinon « pack » serait happé par
# le paramètre de chemin ref_id.
@app.post("/api/references/pack", dependencies=[Depends(require_unlock)])
async def import_pack() -> dict:
    """Indexe le pack de bilans fictifs embarqué (amorces de style).

    Re-cliquer remplace le pack (suppression des « fictif » puis réinsertion) :
    jamais de doublon, et une mise à jour de l'app rafraîchit les exemples.
    Les bilans importés par le praticien (source « import ») sont intouchés."""
    fichiers = importer.pack_fichiers()
    if not fichiers:
        raise HTTPException(500, "Pack d'exemples introuvable dans cette installation.")
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
    # Même chorégraphie en 3 temps que l'import d'un fichier : découpage dans
    # le threadpool, embeddings (réseau local) hors verrou, insertion rapide.
    extraits = await run_in_threadpool(_decouper_pack, fichiers)
    try:
        embs = [await rag.embed(contenu, cfg) for _, _, _, contenu in extraits]
    except rag.EmbeddingUnavailable as exc:
        raise HTTPException(503, str(exc))
    with security.transaction() as con:
        rag.delete_par_source(con, "fictif")
        for (domaine, cle, titre, contenu), emb in zip(extraits, embs):
            rag.add_reference(con, None, "fictif", domaine, cle, titre, contenu, emb)
        security.audit(
            "import_pack", "reference", None,
            f"{len(extraits)} extraits · {len(fichiers)} fichiers",
        )
    return {"n_fichiers": len(fichiers), "n_extraits": len(extraits)}


@app.delete("/api/references/pack", dependencies=[Depends(require_unlock)])
async def delete_pack() -> dict:
    with security.transaction() as con:
        n = rag.delete_par_source(con, "fictif")
        if n:
            security.audit("delete_pack", "reference", None, f"{n} extraits")
    return {"n": n}


@app.delete("/api/references/{ref_id}", dependencies=[Depends(require_unlock)])
async def delete_reference(ref_id: int) -> OkResponse:
    with security.transaction() as con:
        rag.delete(con, ref_id)
        security.audit("delete_reference", "reference", ref_id, "")
    return OkResponse(ok=True)


# --- Modèles disponibles (sélecteur de l'interface) --------------------------

@app.get("/api/models", dependencies=[Depends(require_unlock)])
async def get_models() -> dict:
    """Modèles installés sur l'hôte Ollama *configuré* (et non celui du module) :
    le sélecteur doit refléter la configuration praticien effective."""
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
    try:
        models = await llm.list_models(cfg["llm"].get("host"))
    except httpx.HTTPError:
        raise HTTPException(
            503,
            "Le moteur d'IA local (Ollama) ne répond pas. Vérifiez qu'il est "
            "bien démarré, puis réessayez.",
        )
    return {"models": models, "default": cfg["llm"]["model"]}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
