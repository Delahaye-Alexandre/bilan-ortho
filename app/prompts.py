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
personne pour le patient. Chaque rubrique listée plus bas précise CE QU'ON Y \
RANGE : respecte cette répartition, c'est elle qui fait la structure \
réglementaire du compte-rendu. Ton texte sera AJOUTÉ à la suite du contenu \
existant de la rubrique : ne répète pas ce qui y figure déjà et ne réécris pas \
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
   e) une incohérence ou une information manifestement manquante ;
   f) une rubrique reste vide alors que les éléments fournis contiennent \
manifestement des informations qui s'y rapportent.
Quand le praticien énonce lui-même un diagnostic (ex. « je pense à une \
dyslexie »), reformule-le dans la rubrique « diagnostic » comme une \
proposition à confirmer, et pose une question pour l'étayer par les résultats.
Tes questions portent UNIQUEMENT sur des informations que seul le praticien \
détient sur CE patient. Ne lui demande jamais une norme, un étalonnage \
théorique, une valeur de référence ou une définition : leur interprétation \
relève de sa compétence, pas de la tienne.

RÈGLES IMPÉRATIVES :
- EXHAUSTIVITÉ : tout élément clinique dicté doit se retrouver dans une \
rubrique. Ne résume pas au point d'en perdre. Les étapes du développement \
(marche, premiers mots, association de mots), les antécédents médicaux, ORL, \
audition et vision, le parcours de soin antérieur et les éléments NÉGATIFS \
explicites (« pas d'antécédent ORL », « audition normale », « aucun suivi \
antérieur ») ont une valeur clinique : conserve-les.
- CHIFFRES : n'écris un chiffre (score, écart-type, percentile, note standard, \
âge de lecture, durée, nombre d'erreurs) QUE s'il figure mot pour mot dans les \
éléments fournis. Si une difficulté est évoquée sans chiffre, décris-la \
qualitativement, n'en invente aucun, et pose une question. Ne recalcule ni ne \
modifie aucun chiffre. N'attribue JAMAIS à un test un résultat obtenu à un autre.
- Les scores et étalonnages ne figurent QUE dans la rubrique des épreuves. Les \
rubriques d'analyse, de diagnostic et de projet les commentent sans les répéter.
- NE COMMENCE JAMAIS ton texte par le titre ou la clé de la rubrique : n'écris \
pas « Anamnèse : … » dans la rubrique anamnèse. Le titre est déjà affiché \
au-dessus ; commence directement par le contenu clinique.
- Les repères « à y ranger » servent à choisir la bonne rubrique : ce ne sont \
NI des intertitres à recopier, NI un formulaire à remplir. Rédige en prose \
clinique continue, et n'écris rien sur un point que la dictée n'aborde pas.
- Chaque information ne va que dans UNE seule rubrique, celle où elle est le \
plus à sa place : ne la répète pas d'une rubrique à l'autre.
- N'attribue au patient que ce qui le concerne : les personnes citées dans la \
dictée (enseignant, médecin, parents) sont des tiers, jamais le patient.
- Tu ne poses JAMAIS de diagnostic de ta propre initiative. Tu peux rédiger la \
rubrique « diagnostic » uniquement pour reformuler ce que le praticien a \
explicitement énoncé — jamais pour en déduire un.
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


# Le niveau « standard » était absent de cette table : `.get()` renvoyait None
# et AUCUNE consigne de rédaction n'était transmise au modèle, qui résumait
# alors librement — une anamnèse dictée en détail (développement, antécédents)
# revenait amputée. Les trois niveaux sont désormais explicites.
_NIVEAU_DETAIL = {
    "concis": "Rédige chaque rubrique de façon concise : va à l'essentiel, "
    "en une à deux phrases, mais sans omettre d'élément clinique dicté.",
    "standard": "Rédige chaque rubrique dans le style d'un compte-rendu : des "
    "phrases complètes, reprenant TOUS les éléments dictés qui la concernent, "
    "sans délayer.",
    "detaille": "Rédige chaque rubrique de façon développée (contexte, nuances), "
    "toujours sans rien inventer et sans omettre aucun élément dicté.",
}


# Ce qu'on range dans chaque rubrique du tronc commun. Sans ces repères, le
# modèle ne reçoit que des clés nues (`observations`, `analyse`…) et range au
# jugé : les observations de passation atterrissaient dans « Épreuves »,
# laissant leur propre rubrique vide. Une trame personnalisée peut fournir sa
# propre aide par rubrique (champ `aide`), qui a priorité.
# Reformuler ces repères en listes de mots-clés, pour dissuader le modèle de
# les recopier comme intertitres, a été essayé et MESURÉ : la complétude est
# tombée de 4 passages complets sur 5 à 0 sur 3. La formulation rédigée
# ci-dessous est celle qui tient — le modèle en recopie parfois une étiquette
# (« Suites proposées : … »), défaut cosmétique que le praticien corrige à la
# relecture, sans commune mesure avec un compte-rendu amputé de son diagnostic.
AIDE_RUBRIQUES: dict[str, str] = {
    "administratif": "objet de la demande et qui l'adresse, cadre du bilan, "
    "classe suivie par le patient ou son activité professionnelle ; aucun "
    "résultat ni score",
    "anamnese": "histoire rapportée par le patient ou sa famille : grossesse et "
    "naissance, étapes du développement (marche, premiers mots, association de "
    "mots), antécédents médicaux et ORL, audition, vision, antécédents "
    "familiaux, prises en charge antérieures, plainte actuelle et son "
    "retentissement au quotidien (évitement, refus, fatigue, souffrance)",
    "observations": "comportement pendant la passation : contact, coopération, "
    "attention, fatigabilité, appétence, communication spontanée ; aucun score",
    "epreuves": "tests passés avec leurs résultats et étalonnages chiffrés — "
    "c'est la SEULE rubrique où figurent des scores",
    "analyse": "interprétation clinique croisée : ce qui est déficitaire, ce qui "
    "est préservé, hypothèses explicatives, sans répéter les chiffres",
    "diagnostic": "uniquement la conclusion énoncée par le praticien, reformulée "
    "comme une proposition à confirmer",
    "projet": "suites proposées : rééducation (rythme, durée), axes de travail, "
    "aménagements, réévaluation, orientations",
}


# Mise en forme des textes proposés. Le praticien la contrôle (réglage
# style.mise_en_forme_ia) ; quand elle est permise, elle se calque sur les
# extraits de référence, qui conservent désormais gras, souligné et listes.
MISE_EN_FORME_AUTORISEE = (
    "MISE EN FORME : tu peux utiliser du gras (**texte**), de l'italique "
    "(*texte*), du souligné (<u>texte</u>) et des listes (un élément par ligne, "
    "commençant par « - » ou « 1. »). Jamais de titres, de tableaux ni d'autre "
    "balisage. Reste sobre et calque ta mise en forme sur celle des extraits du "
    "praticien s'il y en a : mets en relief ce qu'il met en relief, ni plus ni "
    "moins. Sans extrait : gras réservé aux noms de tests et aux résultats "
    "saillants, listes réservées aux énumérations (axes de rééducation, "
    "aménagements)."
)
MISE_EN_FORME_INTERDITE = (
    "N'utilise AUCUNE mise en forme : ni astérisques, ni balises, ni listes à "
    "puces — du texte brut uniquement."
)


def aide_rubrique(cle: str, aides: dict[str, str] | None = None) -> str:
    """Repère de contenu d'une rubrique : trame du praticien, sinon défaut."""
    perso = (aides or {}).get(cle)
    return (perso or "").strip() or AIDE_RUBRIQUES.get(cle, "")


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


def _etat_sections(
    sections: list[dict],
    max_car: int = MAX_CAR_SECTION,
    aides: dict[str, str] | None = None,
) -> str:
    """Contenu réel des rubriques (tronqué au besoin) : le LLM doit savoir ce
    qui est déjà connu pour ne pas le redemander ni le répéter — et ce qu'on
    range dans chacune, pour router correctement les éléments nouveaux."""
    lignes = []
    for s in sections:
        entete = f"- {s['cle']} ({s['titre']})"
        aide = aide_rubrique(s["cle"], aides)
        if aide:
            entete += f" — à y ranger : {aide}"
        c = (s.get("contenu") or "").strip()
        if not c:
            lignes.append(f"{entete}\n  contenu actuel : (vide)")
            continue
        if len(c) > max_car:
            c = c[:max_car].rstrip() + " […]"
        lignes.append(f"{entete}\n  contenu actuel : « {c} »")
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
    aides: dict[str, str] | None = None,
) -> str:
    """Message utilisateur : état rédigé des rubriques + mémoire du dialogue de
    clarification + éléments nouveaux (dictée et/ou réponses) + repères cliniques."""
    etat = _etat_sections(sections, max_car_section, aides)
    reperes = ""
    if patient_desc:
        reperes += (
            f"\nInformations patient déjà connues : {patient_desc}. "
            "Ne pose PAS de question à leur sujet ; utilise-les pour interpréter les étalonnages."
        )
    if guidance:
        reperes += f"\nRepères d'évaluation pour ce domaine : {guidance}"
    if tests_connus:
        # Cette liste est fournie pour *reconnaître* un test mal transcrit, pas
        # pour en choisir un : sans la mise en garde, le modèle y puisait le nom
        # le plus proche (« Batelem » dicté → « EVALEO 6-15 » écrit, reproduit
        # deux fois sur deux). `verif_tests` reste le garde-fou déterministe.
        reperes += (
            f"\nTests usuels de ce domaine, donnés pour t'aider à reconnaître un nom "
            f"mal transcrit : {tests_connus}. N'écris JAMAIS un nom de cette liste "
            "qui n'a pas été prononcé ; si le nom entendu ne correspond à aucun "
            "d'eux, reprends-le tel quel."
        )
    if style_prefs:
        detail = _NIVEAU_DETAIL.get(style_prefs.get("niveau_detail", "standard"))
        if detail:
            reperes += f"\n{detail}"
        pronom = "vouvoyant" if style_prefs.get("vouvoiement", True) else "tutoyant"
        reperes += f"\nFormule tes questions au praticien en le {pronom}."
        reperes += "\n" + (
            MISE_EN_FORME_AUTORISEE if style_prefs.get("mise_en_forme_ia", True)
            else MISE_EN_FORME_INTERDITE
        )
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
        f"Rubriques du bilan — ce qu'on y range et leur contenu actuel :\n{etat}"
        f"{dialogue}{nouveaux}\n\n"
        "Propose les ajouts par rubrique et les éventuelles NOUVELLES questions de clarification, en JSON."
    )
