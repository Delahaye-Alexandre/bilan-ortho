"""Client léger pour Ollama (LLM 100 % local)."""
from __future__ import annotations

import difflib
import json
import logging
import os
import re
import unicodedata

import httpx

from . import catalogues, prompts, systeme

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_K_M")


class ModeleIntrouvable(RuntimeError):
    """Le modèle demandé n'est pas téléchargé dans Ollama (404 « model not
    found »). Le message est le nom du modèle."""


class ModeleCloud(RuntimeError):
    """Le modèle configuré est hébergé par Ollama sur Internet : refusé, les
    données patient ne quittent pas la machine. Le message est le nom du
    modèle."""


class ReponseIllisible(RuntimeError):
    """La réponse non vide du modèle n'a pas pu être lue comme du JSON
    (les deux tentatives de parsing ont échoué)."""


async def list_models(host: str | None = None) -> list[str]:
    """Retourne la liste des modèles disponibles localement.

    ``host`` vient de la config praticien (``llm.host``), comme pour la
    structuration : interroger l'hôte du module alors qu'un autre est
    configuré afficherait un sélecteur qui ne correspond à rien."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{host or OLLAMA_HOST}/api/tags")
        resp.raise_for_status()
        data = resp.json()
    return systeme.modeles_locaux(data)


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
    nom = model or OLLAMA_MODEL
    if systeme.nom_modele_cloud(nom):
        raise ModeleCloud(nom)
    options = {"temperature": temperature}
    if num_ctx:
        options["num_ctx"] = int(num_ctx)
    payload = {
        "model": nom,
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
        if resp.status_code == 404:
            # Ollama tourne mais le modèle n'est pas téléchargé : à distinguer
            # d'un Ollama injoignable (le diagnostic et le remède diffèrent).
            raise ModeleIntrouvable(payload["model"])
        resp.raise_for_status()
        data = resp.json()
    return data["message"]["content"]


def _parse_structure(raw: str) -> dict:
    """Parse tolérant de la réponse JSON du modèle (récupère le 1er objet).

    Une réponse non vide dont aucune tentative ne donne un objet JSON lève
    ``ReponseIllisible`` : un succès silencieux avec 0 mise à jour serait
    indistinguable d'un légitime « rien à ajouter »."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict):
        if raw.strip():
            raise ReponseIllisible(
                "La réponse du modèle n'a pas pu être lue. Relancez l'analyse ; "
                "si cela se reproduit, essayez un autre modèle (⚙️ Paramètres)."
            )
        data = {}
    return {
        "updates": _liste_updates(data.get("updates")),
        "questions": _liste_questions(data.get("questions")),
    }


def _liste_objets(brut, cle_valeur: str) -> list[dict]:
    """Normalise ce que le modèle a rendu en liste de dictionnaires.

    Un modèle local rend parfois ``{"updates": {"anamnese": "texte"}}`` au lieu
    d'une liste : l'ancien code levait alors une ``AttributeError`` non
    rattrapée, donc un 500 opaque au praticien."""
    if isinstance(brut, dict):
        return [{"section": k, cle_valeur: v} for k, v in brut.items()]
    if not isinstance(brut, list):
        return []
    return [o for o in brut if isinstance(o, dict)]


def _liste_updates(brut) -> list[dict]:
    """Textes proposés, **sans jamais en écarter un en silence**.

    Un update dont la rubrique est absente ou nulle conservait son texte
    clinique et disparaissait sans trace : c'était le dernier point du pipeline
    où du contenu pouvait s'évaporer. Il est désormais rendu avec une section
    vide — l'appelant le remonte comme « non placé » et l'interface le dit."""
    out = []
    for u in _liste_objets(brut, "texte"):
        texte = (u.get("texte") or "")
        texte = texte.strip() if isinstance(texte, str) else str(texte).strip()
        if not texte:
            continue
        section = u.get("section")
        out.append({"section": section if isinstance(section, str) else "", "texte": texte})
    return out


def _liste_questions(brut) -> list[dict]:
    out = []
    for q in _liste_objets(brut, "question"):
        question = (q.get("question") or "")
        question = question.strip() if isinstance(question, str) else str(question).strip()
        if not question:
            continue
        section = q.get("section") or ""
        pourquoi = q.get("pourquoi") or ""
        out.append({
            "section": section if isinstance(section, str) else "",
            "question": question,
            "pourquoi": pourquoi.strip() if isinstance(pourquoi, str) else "",
        })
    return out


# Seuils de rattachement d'une clé de rubrique approximative (cf. resoudre_cle).
_PREFIXE_MIN = 5    # longueur minimale d'un préfixe commun jugé signifiant
_RATIO_MIN = 0.70   # similarité minimale pour un rapprochement approché
_MARGE_MIN = 0.15   # écart exigé avec le 2e candidat (anti-confusion)


def _norm_cle(s: str) -> str:
    d = unicodedata.normalize("NFD", s or "")
    sans = "".join(c for c in d if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", sans.lower())


def resoudre_cle(brute: str, sections: list[dict]) -> str | None:
    """Rattache la clé de rubrique rendue par le modèle à une clé réelle.

    Mesuré en réel : qwen3.5:4b écrit « euvres » au lieu de « epreuves » dans
    5 passages sur 6. La mise à jour était alors écartée **en silence** et la
    rubrique « Épreuves & résultats » — le cœur clinique du compte-rendu —
    disparaissait sans que rien ne le signale.

    Quatre niveaux, du plus sûr au plus tolérant : égalité stricte, égalité
    une fois normalisée (casse, accents, ponctuation) sur la clé ou le titre,
    plus long préfixe commun s'il est franc et sans rival, puis rapprochement
    approché exigeant une marge nette sur le deuxième candidat.

    Cette marge n'est pas une précaution théorique : `analysesynthese` ressort
    à 0,636 de « analyse » mais 0,609 de « anamnese ». Sans elle, une analyse
    clinique pourrait être rangée dans l'anamnèse — mal router est plus grave
    que ne pas router, puisque l'appelant signale au praticien ce qui n'a pas
    pu être placé."""
    if not brute:
        return None
    cles = [s["cle"] for s in sections]
    if brute in cles:
        return brute
    n = _norm_cle(brute)
    if not n:
        return None
    for s in sections:
        if n in (_norm_cle(s["cle"]), _norm_cle(s["titre"])):
            return s["cle"]
    par_norme = {_norm_cle(c): c for c in cles if _norm_cle(c)}

    def prefixe_commun(a: str, b: str) -> int:
        i = 0
        while i < min(len(a), len(b)) and a[i] == b[i]:
            i += 1
        return i

    # « analysesynthese » → analyse, « observationclinique » → observations :
    # un préfixe franc et unique est un signal plus fiable que la similarité.
    prefixes = sorted(
        ((prefixe_commun(n, norme), norme) for norme in par_norme), reverse=True
    )
    if prefixes and prefixes[0][0] >= _PREFIXE_MIN and (
        len(prefixes) == 1 or prefixes[0][0] > prefixes[1][0]
    ):
        return par_norme[prefixes[0][1]]

    # « euvres » → epreuves : similarité franche ET nettement détachée.
    scores = sorted(
        ((difflib.SequenceMatcher(None, n, norme).ratio(), norme) for norme in par_norme),
        reverse=True,
    )
    if not scores or scores[0][0] < _RATIO_MIN:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < _MARGE_MIN:
        return None
    return par_norme[scores[0][1]]


# En deçà de cette part du matériau du tour, la réponse du modèle est jugée
# vraisemblablement interrompue (cf. couverture_suspecte).
_COUVERTURE_MIN = 0.35
_COUVERTURE_SOURCE_MIN = 500


def couverture_suspecte(
    nouveau: str, updates: list[dict], seuil: float = _COUVERTURE_MIN
) -> bool:
    """La réponse du modèle a-t-elle vraisemblablement été interrompue ?

    Mesuré contre qwen3.5:4b sur une dictée de ~1 900 caractères : un passage
    complet propose 1 600 à 1 770 caractères (85-93 %), un passage amputé n'en
    propose que 620 (33 %), parfois 106 (6 %) — le compte-rendu part alors sans
    son diagnostic ni son projet thérapeutique.

    Rien ne permet de le détecter côté transport : Ollama répond
    ``done_reason: "stop"``, il n'y a pas de troncature technique. Le modèle
    décide simplement de s'arrêter. On ne relance donc pas d'office (ce serait
    doubler une attente déjà longue à l'insu du praticien) : on le signale, et
    il relance d'un clic.

    Une dictée courte remplit légitimement peu de rubriques : en dessous de
    ``_COUVERTURE_SOURCE_MIN`` caractères, aucun jugement n'est porté."""
    source = (nouveau or "").strip()
    if len(source) < _COUVERTURE_SOURCE_MIN:
        return False
    propose = sum(len((u.get("texte") or "").strip()) for u in updates)
    return propose < seuil * len(source)


# Estimation grossière mais suffisante : en français, un tokenizer BPE produit
# environ un token pour trois caractères. On ne cherche pas la valeur exacte —
# seulement à savoir qu'on approche du plafond.
_CAR_PAR_TOKEN = 3.0
_PART_CONTEXTE_ALERTE = 0.9


def prompt_depasse_contexte(system: str, user: str, num_ctx) -> bool:
    """Le prompt approche-t-il la fenêtre de contexte du modèle ?

    Au-delà, Ollama tronque le **début** du prompt — donc les consignes système :
    les règles CHIFFRES, EXHAUSTIVITÉ et l'interdiction de poser un diagnostic
    partent les premières, tandis que ``format:"json"`` maintient une sortie
    bien formée. Rien ne trahit alors la perte : d'où ce contrôle, signalé au
    praticien au même titre qu'une rubrique tronquée."""
    try:
        plafond = int(num_ctx or 0)
    except (TypeError, ValueError):
        return False
    if plafond <= 0:
        return False
    tokens = (len(system) + len(user)) / _CAR_PAR_TOKEN
    return tokens > _PART_CONTEXTE_ALERTE * plafond


def _aides_trame(cfg: dict) -> dict[str, str]:
    """Repères « à y ranger » définis par le praticien dans sa trame (champ
    `aide` d'une rubrique). Les rubriques sans aide retombent sur les repères
    intégrés de `prompts.AIDE_RUBRIQUES`."""
    sections = ((cfg.get("trame") or {}).get("sections")) or []
    return {
        s["cle"]: str(s.get("aide") or "")
        for s in sections
        if isinstance(s, dict) and s.get("cle")
    }


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
    Retourne ``{"updates": [...], "questions": [...], "rubriques_tronquees":
    [clés]}`` — cette dernière liste signale les rubriques trop longues,
    transmises seulement en partie au modèle. Ne conserve que des clés de
    section valides.
    """
    from . import config as _config

    llmcfg = cfg["llm"]
    try:
        max_car = int(llmcfg.get("max_car_section") or prompts.MAX_CAR_SECTION)
    except (TypeError, ValueError):
        max_car = prompts.MAX_CAR_SECTION
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
        max_car_section=max_car,
        aides=_aides_trame(cfg),
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
    # Rattachement des clés rendues par le modèle. Ce qui ne se rattache à
    # aucune rubrique n'est plus jeté en silence : la liste remonte à
    # l'interface, qui le dit au praticien — un texte clinique perdu sans un
    # mot est le pire des deux maux.
    placees, non_placees = [], []
    for u in result["updates"]:
        cle = resoudre_cle(u["section"], sections)
        if cle:
            placees.append({**u, "section": cle})
        else:
            non_placees.append(u["section"] or "rubrique non précisée")
            logger.warning(
                "Rubrique inconnue rendue par le modèle : %r — texte non placé (%d car.)",
                u["section"], len(u["texte"]),
            )
    result["updates"] = placees
    result["updates_non_placees"] = non_placees
    result["prompt_trop_long"] = prompt_depasse_contexte(
        system, user, llmcfg.get("num_ctx")
    )
    result["questions"] = [
        q for q in result["questions"]
        if (not q["section"] or resoudre_cle(q["section"], sections))
    ]
    result["rubriques_tronquees"] = prompts.sections_tronquees(sections, max_car)
    return result
