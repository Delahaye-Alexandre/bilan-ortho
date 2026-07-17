"""Client léger pour Ollama (LLM 100 % local)."""
from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator

import httpx

from . import catalogues, prompts

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_K_M")


async def list_models() -> list[str]:
    """Retourne la liste des modèles disponibles localement."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{OLLAMA_HOST}/api/tags")
        resp.raise_for_status()
        data = resp.json()
    return [m["name"] for m in data.get("models", [])]


async def generate_stream(
    prompt: str,
    system: str,
    model: str | None = None,
    temperature: float = 0.3,
) -> AsyncIterator[str]:
    """Génère du texte en streaming via l'API /api/generate d'Ollama.

    Émet des fragments de texte au fur et à mesure. Une température basse
    limite les « inventions » du modèle, ce qui est souhaitable en contexte
    clinique.
    """
    payload = {
        "model": model or OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": True,
        "options": {"temperature": temperature},
    }
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{OLLAMA_HOST}/api/generate", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("response"):
                    yield chunk["response"]
                if chunk.get("done"):
                    break


async def chat_json(
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.2,
    host: str | None = None,
    num_ctx: int | None = None,
    timeout_s: float | None = 600,
) -> str:
    """Appel Ollama /api/chat en mode JSON forcé (non streamé). Retourne le texte.

    ``num_ctx`` doit couvrir prompt + réponse : sans lui, Ollama applique son
    défaut (~4k) et TRONQUE silencieusement le début du prompt — donc les
    consignes système — dès que l'ensemble dépasse.

    ``timeout_s`` borne l'attente : sans lui, un Ollama gelé suspendait
    l'interface à l'infini (audit)."""
    options = {"temperature": temperature}
    if num_ctx:
        options["num_ctx"] = int(num_ctx)
    payload = {
        "model": model or OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": "json",
        "stream": False,
        "options": options,
        # Modèles à raisonnement (qwen3.5…) : réponse directe exigée, sinon
        # des minutes de « réflexion » sur CPU avant le JSON.
        "think": False,
    }
    timeout = httpx.Timeout(timeout_s or 600, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        url = f"{host or OLLAMA_HOST}/api/chat"
        resp = await client.post(url, json=payload)
        if resp.status_code == 400:
            # Vieil Ollama qui rejette le champ `think` : réessai sans.
            payload.pop("think", None)
            resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data["message"]["content"]


def _parse_structure(raw: str) -> dict:
    """Parse tolérant de la réponse JSON du modèle (récupère le 1er objet)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
    updates = [
        {"section": u.get("section"), "texte": (u.get("texte") or "").strip()}
        for u in (data.get("updates") or [])
        if u.get("section") and (u.get("texte") or "").strip()
    ]
    questions = [
        {
            "section": q.get("section") or "",
            "question": (q.get("question") or "").strip(),
            "pourquoi": (q.get("pourquoi") or "").strip(),
        }
        for q in (data.get("questions") or [])
        if (q.get("question") or "").strip()
    ]
    return {"updates": updates, "questions": questions}


async def structure(
    transcription: str, sections: list[dict], domaines: list[str], cfg: dict,
    style_examples: list[str] | None = None, patient_desc: str = "",
    reponses: list[dict] | None = None,
    questions_en_attente: list[str] | None = None,
    questions_ecartees: list[str] | None = None,
    questions_repondues: list[str] | None = None,
) -> dict:
    """Route une dictée et/ou des réponses de clarification vers les rubriques
    + génère les nouvelles questions de clarification.

    ``domaines`` = liste de clés de domaine (pour injecter repères + tests connus).
    Les listes de questions (en attente/écartées/répondues) donnent au LLM la
    mémoire du dialogue pour qu'il ne repose pas les mêmes questions.
    Retourne ``{"updates": [{section, texte}], "questions": [{section, question, pourquoi}]}``.
    Ne conserve que des clés de section valides.
    """
    from . import config as _config

    llmcfg = cfg["llm"]
    valid = {s["cle"] for s in sections}
    titres_map = {d["cle"]: d["titre"] for d in _config.DOMAINES}
    domaine_titres = ", ".join(titres_map.get(c, c) for c in domaines)
    cles = ", ".join(sorted(valid))
    custom = (cfg.get("prompts") or {}).get("structure_system") or ""
    # Prompt personnalisé : {cles} est substitué tel quel (pas de .format, pour
    # que les accolades du JSON d'exemple n'aient pas à être échappées).
    system = custom.replace("{cles}", cles) if custom.strip() \
        else prompts.STRUCTURE_SYSTEM.format(cles=cles)
    user = prompts.build_structure_user(
        transcription, sections, domaine_titres,
        guidance=catalogues.guidance(domaines, cfg),
        tests_connus=", ".join(catalogues.tests_noms(domaines, cfg)),
        style_examples=style_examples,
        style_prefs=cfg.get("style"),
        patient_desc=patient_desc,
        reponses=reponses,
        questions_en_attente=questions_en_attente,
        questions_ecartees=questions_ecartees,
        questions_repondues=questions_repondues,
    )
    raw = await chat_json(
        system, user,
        model=llmcfg["model"],
        temperature=float(llmcfg.get("temperature", 0.2)),
        host=llmcfg.get("host"),
        num_ctx=llmcfg.get("num_ctx"),
        timeout_s=llmcfg.get("timeout_s"),
    )
    result = _parse_structure(raw)
    result["updates"] = [u for u in result["updates"] if u["section"] in valid]
    result["questions"] = [
        q for q in result["questions"] if (not q["section"] or q["section"] in valid)
    ]
    return result
