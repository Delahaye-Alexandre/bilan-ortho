"""Gabarits de prompts pour la structuration des bilans orthophoniques.

Le LLM répartit une dictée libre (et les réponses aux questions de
clarification) dans les rubriques du bilan. Style attendu : clinique, sobre,
en français, sans invention.
"""

# --- Structuration d'une dictée libre + questions de clarification ----------

STRUCTURE_SYSTEM = """Tu es un assistant de rédaction pour un·e orthophoniste \
diplômé·e. On te donne l'état d'un bilan orthophonique en cours (le contenu déjà \
rédigé de ses rubriques), puis les éléments nouveaux de ce tour : une dictée \
libre et/ou des réponses du praticien à tes questions de clarification. Tu as \
DEUX tâches :

1. RÉPARTIR les éléments nouveaux dans les bonnes rubriques et proposer, pour \
chacune concernée, un texte rédigé : clinique, sobre, en français, à la 3e \
personne pour le patient. Ton texte sera AJOUTÉ à la suite du contenu existant \
de la rubrique : ne répète pas ce qui y figure déjà et ne réécris pas \
l'existant. N'INVENTE RIEN : utilise uniquement ce qui a été dicté ou répondu. \
Pour une réponse à une question, rédige l'information en une phrase complète et \
autonome, dans la rubrique visée par la question quand elle est indiquée.

2. REPÉRER les zones d'ombre et formuler des QUESTIONS de clarification \
ciblées. Vérifie SYSTÉMATIQUEMENT chacun de ces points et pose une question dès \
que le cas s'applique ET que la réponse ne figure ni dans le contenu des \
rubriques ni dans les éléments nouveaux :
   a) l'âge ou la date de naissance du patient n'est pas connu (indispensable \
pour interpréter tout étalonnage) ;
   b) un score/résultat est évoqué SANS étalonnage chiffré (écart-type, \
percentile, note standard, âge de lecture) ;
   c) un test est nommé mais son résultat n'est pas donné ;
   d) une appréciation est vague (« très en dessous », « catastrophique », \
« ça va ») sans chiffre ni précision ;
   e) une incohérence ou une information manifestement manquante.
Quand le praticien énonce lui-même un diagnostic (ex. « je pense à une \
dyslexie »), reformule-le dans la rubrique « diagnostic » comme une \
proposition à confirmer, et pose une question pour l'étayer par les résultats.

RÈGLES IMPÉRATIVES :
- Tu ne poses JAMAIS de diagnostic de ta propre initiative. Tu peux rédiger la \
rubrique « diagnostic » uniquement pour reformuler ce que le praticien a \
explicitement énoncé — jamais pour en déduire un.
- Ne recalcule ni ne modifie aucun chiffre.
- Si une rubrique n'est pas concernée par les éléments nouveaux, ne l'inclus pas.
- Préfère poser une question plutôt qu'inventer une donnée manquante.
- NE REPOSE JAMAIS une question dont la réponse figure déjà dans les rubriques \
ou dans les éléments de ce tour.
- NE REPOSE JAMAIS une question listée comme « en attente », « déjà répondue » \
ou « écartée » — ni à l'identique, ni reformulée. Les questions en attente \
restent affichées au praticien : inutile de les répéter.
- Si aucune question nouvelle ne s'impose, renvoie une liste "questions" vide.

Réponds STRICTEMENT en JSON valide, sans texte autour, au format :
{{"updates":[{{"section":"<cle>","texte":"<texte proposé>"}}],\
"questions":[{{"section":"<cle>","question":"<question>","pourquoi":"<raison brève>"}}]}}

Les seules clés de section valides sont : {cles}."""


_NIVEAU_DETAIL = {
    "concis": "Rédige chaque rubrique de façon concise : 1 à 2 phrases, l'essentiel.",
    "detaille": "Rédige chaque rubrique de façon développée (contexte, nuances), "
    "toujours sans rien inventer.",
}


# Repli si la config ne fournit pas de seuil (la valeur de référence vit dans
# les défauts de config : llm.max_car_section).
MAX_CAR_SECTION = 1500


def sections_tronquees(sections: list[dict], max_car: int = MAX_CAR_SECTION) -> list[str]:
    """Clés des rubriques dont le contenu dépasse le seuil : elles ne seront
    transmises que partiellement au modèle — l'appelant doit le signaler."""
    return [
        s["cle"] for s in sections
        if len((s.get("contenu") or "").strip()) > max_car
    ]


def _etat_sections(sections: list[dict], max_car: int = MAX_CAR_SECTION) -> str:
    """Contenu réel des rubriques (tronqué au besoin) : le LLM doit savoir ce
    qui est déjà connu pour ne pas le redemander ni le répéter."""
    lignes = []
    for s in sections:
        c = (s.get("contenu") or "").strip()
        if not c:
            lignes.append(f"- {s['cle']} ({s['titre']}) : (vide)")
            continue
        if len(c) > max_car:
            c = c[:max_car].rstrip() + " […]"
        lignes.append(f"- {s['cle']} ({s['titre']}) :\n« {c} »")
    return "\n".join(lignes)


def _bloc_questions(titre: str, questions: list[str] | None) -> str:
    if not questions:
        return ""
    return f"\n\n{titre}\n" + "\n".join(f"- {q.strip()}" for q in questions if q.strip())


def build_structure_user(
    transcription: str,
    sections: list[dict],
    domaine_titres: str,
    guidance: str = "",
    tests_connus: str = "",
    style_examples: list[str] | None = None,
    style_prefs: dict | None = None,
    patient_desc: str = "",
    reponses: list[dict] | None = None,
    questions_en_attente: list[str] | None = None,
    questions_ecartees: list[str] | None = None,
    questions_repondues: list[str] | None = None,
    max_car_section: int = MAX_CAR_SECTION,
) -> str:
    """Message utilisateur : état rédigé des rubriques + mémoire du dialogue de
    clarification + éléments nouveaux (dictée et/ou réponses) + repères cliniques."""
    etat = _etat_sections(sections, max_car_section)
    reperes = ""
    if patient_desc:
        reperes += (
            f"\nInformations patient déjà connues : {patient_desc}. "
            "Ne pose PAS de question à leur sujet ; utilise-les pour interpréter les étalonnages."
        )
    if guidance:
        reperes += f"\nRepères d'évaluation pour ce domaine : {guidance}"
    if tests_connus:
        reperes += f"\nTests usuels de ce domaine (reconnais-les s'ils sont cités) : {tests_connus}"
    if style_prefs:
        detail = _NIVEAU_DETAIL.get(style_prefs.get("niveau_detail", "standard"))
        if detail:
            reperes += f"\n{detail}"
        pronom = "vouvoyant" if style_prefs.get("vouvoiement", True) else "tutoyant"
        reperes += f"\nFormule tes questions au praticien en le {pronom}."
    if style_examples:
        ex = "\n---\n".join(style_examples)
        reperes += (
            "\n\nExtraits de bilans passés du praticien — inspire-toi de LEUR STYLE "
            "de rédaction (tournures, niveau de détail), PAS de leur contenu. "
            "Ils concernent D'AUTRES patients : n'y fais JAMAIS référence dans tes "
            "textes ni dans tes questions (leurs tests et scores n'existent pas "
            "dans le dossier actuel) :\n" + ex
        )
    dialogue = _bloc_questions(
        "Questions de clarification EN ATTENTE (déjà affichées au praticien — ne les repose pas, même reformulées) :",
        questions_en_attente,
    )
    dialogue += _bloc_questions(
        "Questions DÉJÀ RÉPONDUES précédemment (l'information est dans les rubriques — ne les repose pas) :",
        questions_repondues,
    )
    dialogue += _bloc_questions(
        "Questions ÉCARTÉES par le praticien (il ne souhaite pas y répondre — ne les repose JAMAIS) :",
        questions_ecartees,
    )
    nouveaux = ""
    if reponses:
        lignes = []
        for r in reponses:
            cible = f" (rubrique visée : {r['section']})" if r.get("section") else ""
            lignes.append(f"- Question{cible} : « {r['question'].strip()} »\n  Réponse : « {r['reponse'].strip()} »")
        nouveaux += (
            "\n\nRéponses du praticien à tes questions de clarification, à intégrer aux rubriques :\n"
            + "\n".join(lignes)
        )
    if transcription.strip():
        nouveaux += f"\n\nTranscription de la dictée :\n---\n{transcription.strip()}\n---"
    return (
        f"Domaine(s) du bilan : {domaine_titres or 'non précisé'}{reperes}\n\n"
        f"Rubriques et leur contenu actuel :\n{etat}"
        f"{dialogue}{nouveaux}\n\n"
        "Propose les ajouts par rubrique et les éventuelles NOUVELLES questions de clarification, en JSON."
    )
