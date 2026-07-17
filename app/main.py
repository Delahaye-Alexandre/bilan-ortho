"""Serveur FastAPI — assistant local de rédaction de bilans orthophoniques.

100 % local (bind 127.0.0.1). Les fonctions manipulant des données patient sont
protégées par un déverrouillage (base chiffrée). La génération de texte à partir
de notes reste disponible (elle ne touche pas la base).
"""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import (
    FileResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import (
    bilan,
    catalogues,
    config,
    cotation,
    export,
    importer,
    llm,
    patient,
    rag,
    sauvegarde,
    security,
    stt,
    systeme,
)
from .models import (
    BilanCreate,
    ConfigPatch,
    EpreuveCreate,
    GenerateRequest,
    OkResponse,
    PatientIn,
    SectionPut,
    StatusResponse,
    StatutPut,
    StructureRequest,
    UnlockRequest,
)
from .prompts import SECTIONS, SYSTEM_PROMPT, build_prompt

STATIC_DIR = Path(__file__).parent / "static"

from . import __version__

app = FastAPI(title="Bilan Ortho", version=__version__)

# Anti « DNS rebinding » : un site malveillant ouvert dans un autre onglet
# peut faire pointer son domaine vers 127.0.0.1 et interroger ce serveur
# depuis le navigateur. On rejette toute requête dont l'en-tête Host n'est
# pas explicitement la machine locale.
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"]
)

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


@app.post("/api/unlock")
async def unlock(req: UnlockRequest) -> OkResponse:
    if not req.passphrase.strip():
        raise HTTPException(400, "Passphrase vide.")
    if not security.db_exists() and len(req.passphrase) < PASSPHRASE_MIN:
        raise HTTPException(
            400,
            f"Passphrase trop courte : {PASSPHRASE_MIN} caractères minimum "
            "pour protéger le coffre.",
        )
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
    return config.DEFAULTS


@app.get("/api/installation")
async def etat_installation() -> dict:
    return await run_in_threadpool(systeme.etat_installation, _cfg_courante())


@app.post("/api/installation/pull")
async def pull_modele(req: dict) -> StreamingResponse:
    """Télécharge un modèle Ollama en relayant la progression (NDJSON)."""
    nom = (req or {}).get("modele", "")
    if not systeme.nom_modele_valide(nom):
        raise HTTPException(400, "Nom de modèle invalide.")
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
    """Surcharges praticien seules (sans les défauts) — pour l'éditeur avancé."""
    with security.transaction() as con:
        return config.ConfigStore(con).overrides()


@app.get("/api/domaines")
async def get_domaines() -> list[dict]:
    return config.DOMAINES


# --- Dictée vocale locale ----------------------------------------------------

@app.get("/api/stt/info", dependencies=[Depends(require_unlock)])
async def stt_info() -> dict:
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
    return stt.resolved(cfg)


@app.post("/api/transcribe", dependencies=[Depends(require_unlock)])
async def transcribe(audio: UploadFile = File(...)) -> dict:
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Audio vide.")
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
    try:
        result = await run_in_threadpool(stt.transcribe, data, audio.filename or "", cfg)
    except stt.STTUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:  # pragma: no cover - erreurs modèle/audio
        raise HTTPException(500, f"Échec de la transcription : {exc}")
    try:
        with security.transaction() as con:
            # Journalise l'acte, jamais le contenu.
            security.audit("transcribe", "dictee", None, f"{len(result['text'])} car.")
    except RuntimeError:
        # Coffre verrouillé pendant la transcription : 423 explicite plutôt
        # qu'un 500 opaque (l'UI ré-affiche l'écran de verrouillage).
        raise HTTPException(423, "Application verrouillée pendant la transcription.")
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
    try:
        return await run_in_threadpool(_creer)
    except RuntimeError:
        raise HTTPException(423, "Application verrouillée.")
    except Exception as exc:
        raise HTTPException(500, f"Échec de la sauvegarde : {exc}")


@app.get("/api/sauvegardes", dependencies=[Depends(require_unlock)])
async def list_sauvegardes() -> dict:
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
        return sauvegarde.liste(con, cfg)


# --- Bilans & structuration IA ----------------------------------------------

@app.post("/api/bilans", dependencies=[Depends(require_unlock)])
async def create_bilan(req: BilanCreate) -> dict:
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
        bid = bilan.create(
            con, req.domaines, req.type.value, req.patient_id, req.motif, cfg
        )
        security.audit("create", "bilan", bid, "")
        return bilan.get(con, bid)


@app.get("/api/bilans", dependencies=[Depends(require_unlock)])
async def list_bilans() -> list[dict]:
    with security.transaction() as con:
        return bilan.liste(con)


@app.get("/api/bilans/{bilan_id}", dependencies=[Depends(require_unlock)])
async def get_bilan(bilan_id: int) -> dict:
    with security.transaction() as con:
        b = bilan.get(con, bilan_id)
    if not b:
        raise HTTPException(404, "Bilan introuvable.")
    return b


@app.post("/api/bilans/{bilan_id}/structure", dependencies=[Depends(require_unlock)])
async def structure_bilan(bilan_id: int, req: StructureRequest) -> dict:
    if not req.transcription.strip() and not req.reponses:
        raise HTTPException(400, "Rien à structurer : ni dictée, ni réponse.")
    with security.transaction() as con:
        b = bilan.get(con, bilan_id)
        cfg = config.ConfigStore(con).effective()
    if not b:
        raise HTTPException(404, "Bilan introuvable.")
    # Texte de ce tour (dictée + réponses) : sert à retrouver des extraits proches.
    texte_tour = " ".join(
        [req.transcription.strip()]
        + [f"{r.question} {r.reponse}" for r in req.reponses]
    ).strip()
    # Récupère des extraits du praticien pour inspirer le style (best-effort).
    # L'embedding (appel réseau) est calculé HORS du verrou : un Ollama lent
    # ne gèle plus le serveur (audit C3).
    style = []
    try:
        dom = b["domaines"][0] if b["domaines"] else None
        k = cfg["style"]["few_shot_k"]
        if texte_tour and k:
            emb = await rag.embed(texte_tour, cfg)
            with security.transaction() as con:
                refs = rag.retrieve(con, emb, domaine=dom, k=k)
            style = [r["texte"][:800] for r in refs]
    except Exception:
        style = []
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
    except httpx.TimeoutException:
        raise HTTPException(
            504,
            "Le modèle n'a pas répondu dans le délai imparti. Réessayez, ou "
            "choisissez un modèle plus léger (⚙️ Paramètres).",
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Ollama injoignable. Lancez « ollama serve ».")
    try:
        with security.transaction() as con:
            bilan.apply_updates(con, bilan_id, result["updates"])
            security.audit(
                "structure", "bilan", bilan_id,
                f"{len(result['updates'])} maj, {len(result['questions'])} questions"
                + (f", {len(req.reponses)} réponse(s) intégrée(s)" if req.reponses else ""),
            )
            b2 = bilan.get(con, bilan_id)
    except RuntimeError:
        # Coffre verrouillé pendant l'analyse : 423 explicite, résultat non
        # appliqué (la dictée reste dans l'interface, rien n'est perdu).
        raise HTTPException(423, "Application verrouillée pendant l'analyse.")
    return {"bilan": b2, "questions": result["questions"]}


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
        security.audit(
            "statut", "bilan", bilan_id,
            req.statut.value + (f" → {req.destinataire}" if req.destinataire else ""),
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
        resultats = [r.model_dump() for r in req.resultats]
        bilan.add_epreuve(con, bilan_id, req.domaine, req.test_nom, req.version, resultats, cfg)
        security.audit("epreuve", "bilan", bilan_id, req.test_nom)
        return bilan.get(con, bilan_id)


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
async def export_bilan(bilan_id: int, format: str = "md"):
    with security.transaction() as con:
        b = bilan.get(con, bilan_id)
    if not b:
        raise HTTPException(404, "Bilan introuvable.")
    fname = f"bilan-{bilan_id}"
    if format == "docx":
        data = export.to_docx(b)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{fname}.docx"'},
        )
    if format == "txt":
        return PlainTextResponse(
            export.to_txt(b),
            headers={"Content-Disposition": f'attachment; filename="{fname}.txt"'},
        )
    return PlainTextResponse(
        export.to_markdown(b),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}.md"'},
    )


# --- Base de bilans de référence (mémoire / style du praticien) -------------

@app.post("/api/references", dependencies=[Depends(require_unlock)])
async def import_reference(
    file: UploadFile = File(...), domaine: str = Form("")
) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(400, "Fichier vide.")
    with security.transaction() as con:
        cfg = config.ConfigStore(con).effective()
    # 1. Extraction du texte (PDF/OCR : potentiellement plusieurs minutes)
    #    dans le threadpool — l'event loop reste réactif.
    try:
        chunks = await run_in_threadpool(importer.decouper, data, file.filename or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # 2. Embeddings (réseau) hors verrou : la dictée et le keepalive
    #    continuent de répondre pendant l'indexation.
    try:
        embs = [await rag.embed(contenu, cfg) for _, _, contenu in chunks]
    except rag.EmbeddingUnavailable as exc:
        raise HTTPException(503, str(exc))
    # 3. Insertion rapide sous verrou.
    try:
        with security.transaction() as con:
            for (cle, titre, contenu), emb in zip(chunks, embs):
                rag.add_reference(con, None, "import", domaine, cle, titre, contenu, emb)
            security.audit(
                "import_reference", "reference", None,
                f"{len(chunks)} extraits · {file.filename}",
            )
    except RuntimeError:
        raise HTTPException(423, "Application verrouillée pendant l'import.")
    return {
        "n": len(chunks),
        "sections": [c[0] for c in chunks],
        "filename": file.filename or "",
    }


@app.get("/api/references", dependencies=[Depends(require_unlock)])
async def list_references() -> list[dict]:
    with security.transaction() as con:
        return rag.liste(con)


@app.delete("/api/references/{ref_id}", dependencies=[Depends(require_unlock)])
async def delete_reference(ref_id: int) -> OkResponse:
    with security.transaction() as con:
        rag.delete(con, ref_id)
        security.audit("delete_reference", "reference", ref_id, "")
    return OkResponse(ok=True)


# --- Génération de texte (existant) -----------------------------------------

@app.get("/api/sections")
async def get_sections() -> dict[str, str]:
    return {key: titre for key, (titre, _) in SECTIONS.items()}


@app.get("/api/models")
async def get_models() -> dict:
    try:
        models = await llm.list_models()
    except httpx.HTTPError:
        raise HTTPException(503, "Ollama injoignable. Lancez « ollama serve ».")
    return {"models": models, "default": llm.OLLAMA_MODEL}


@app.post("/api/generate")
async def generate(req: GenerateRequest) -> StreamingResponse:
    if req.section not in SECTIONS:
        raise HTTPException(400, f"Section inconnue : {req.section}")
    if not req.notes.strip():
        raise HTTPException(400, "Les notes cliniques sont vides.")

    prompt = build_prompt(req.section, req.notes, req.contexte)

    async def token_stream():
        try:
            async for token in llm.generate_stream(
                prompt, SYSTEM_PROMPT, model=req.model, temperature=req.temperature
            ):
                yield token
        except httpx.HTTPError as exc:  # pragma: no cover
            yield f"\n\n[Erreur Ollama : {exc}]"

    return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
