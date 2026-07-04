"""Gabarits de prompts pour la rédaction de bilans orthophoniques.

Chaque section décrit ce que le LLM doit produire à partir des *notes libres*
du praticien. Le style attendu est clinique, sobre, en français, sans invention.
"""

SYSTEM_PROMPT = """Tu es un assistant de rédaction destiné à un·e orthophoniste \
diplômé·e. Ta tâche est de transformer des notes cliniques brutes en un texte \
de bilan clair, professionnel et rédigé en français.

Règles impératives :
- N'INVENTE JAMAIS de données (résultats de tests, âges, scores, antécédents). \
Utilise uniquement les informations présentes dans les notes. Si une information \
manque, ne la mentionne pas ou écris « [à compléter] ».
- Ne pose aucun diagnostic médical de ta propre initiative ; reformule ce que \
l'orthophoniste a noté.
- Style : phrases claires, vocabulaire clinique orthophonique, ton neutre et \
factuel, à la 3e personne pour le patient.
- N'ajoute pas de conclusion ou de recommandation qui ne découle pas des notes.
- Réponds UNIQUEMENT avec le texte de la section demandée, sans préambule ni \
commentaire de ta part."""


# Sections proposées (clé -> (titre, consigne de rédaction))
SECTIONS: dict[str, tuple[str, str]] = {
    "anamnese": (
        "Anamnèse",
        "Rédige l'anamnèse : motif de consultation, développement, antécédents "
        "médicaux et familiaux pertinents, contexte scolaire/professionnel et "
        "environnemental, en te basant strictement sur les notes.",
    ),
    "plainte": (
        "Motif et plaintes",
        "Rédige le motif de la consultation et les plaintes rapportées "
        "(par le patient, la famille ou les partenaires).",
    ),
    "observation": (
        "Observations cliniques",
        "Rédige les observations cliniques qualitatives (comportement, "
        "attention, communication, versant expressif/réceptif, etc.).",
    ),
    "tests": (
        "Épreuves et résultats",
        "Présente de façon structurée les épreuves/tests administrés et leurs "
        "résultats tels que notés (scores, écarts-types, percentiles). Ne "
        "recalcule rien et ne modifie aucun chiffre.",
    ),
    "synthese": (
        "Synthèse",
        "Rédige une synthèse clinique reliant les observations et les résultats, "
        "sans introduire d'élément absent des notes.",
    ),
    "conclusion": (
        "Conclusion",
        "Rédige la conclusion du bilan à partir de la synthèse fournie dans les "
        "notes. Reste prudent et factuel.",
    ),
    "projet": (
        "Projet thérapeutique",
        "Rédige les propositions de prise en charge / projet thérapeutique "
        "(objectifs, rythme, modalités) uniquement d'après les notes.",
    ),
}


# --- Structuration d'une dictée libre + questions de clarification ----------

STRUCTURE_SYSTEM = """Tu es un assistant de rédaction pour un·e orthophoniste \
diplômé·e. On te donne la transcription d'une dictée libre et la liste des \
rubriques d'un bilan orthophonique. Tu as DEUX tâches :

1. RÉPARTIR les propos dictés dans les bonnes rubriques et proposer, pour \
chacune concernée, un texte rédigé : clinique, sobre, en français, à la 3e \
personne pour le patient. N'INVENTE RIEN : utilise uniquement ce qui a été \
dicté. N'ajoute pas d'information absente.

2. REPÉRER les zones d'ombre et formuler des QUESTIONS de clarification \
ciblées. Vérifie SYSTÉMATIQUEMENT chacun de ces points et pose une question dès \
que le cas s'applique :
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
- Si une rubrique n'est pas concernée par la dictée, ne l'inclus pas.
- Préfère poser une question plutôt qu'inventer une donnée manquante.

Réponds STRICTEMENT en JSON valide, sans texte autour, au format :
{{"updates":[{{"section":"<cle>","texte":"<texte proposé>"}}],\
"questions":[{{"section":"<cle>","question":"<question>","pourquoi":"<raison brève>"}}]}}

Les seules clés de section valides sont : {cles}."""


_NIVEAU_DETAIL = {
    "concis": "Rédige chaque rubrique de façon concise : 1 à 2 phrases, l'essentiel.",
    "detaille": "Rédige chaque rubrique de façon développée (contexte, nuances), "
    "toujours sans rien inventer.",
}


def build_structure_user(
    transcription: str,
    sections: list[dict],
    domaine_titres: str,
    guidance: str = "",
    tests_connus: str = "",
    style_examples: list[str] | None = None,
    style_prefs: dict | None = None,
    patient_desc: str = "",
) -> str:
    """Message utilisateur : dictée + état des rubriques + domaine + repères cliniques."""
    etat = "\n".join(
        f"- {s['cle']} ({s['titre']}) : "
        + (f"{len(s.get('contenu', ''))} car. déjà rédigés" if s.get("contenu") else "vide")
        for s in sections
    )
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
            "de rédaction (tournures, niveau de détail), PAS de leur contenu :\n" + ex
        )
    return (
        f"Domaine(s) du bilan : {domaine_titres or 'non précisé'}{reperes}\n\n"
        f"Rubriques et leur état :\n{etat}\n\n"
        f"Transcription de la dictée :\n---\n{transcription.strip()}\n---\n\n"
        "Propose les ajouts par rubrique et les questions de clarification, en JSON."
    )


def build_prompt(section: str, notes: str, contexte: str = "") -> str:
    """Construit le prompt utilisateur pour une section donnée."""
    if section not in SECTIONS:
        raise ValueError(f"Section inconnue : {section}")
    titre, consigne = SECTIONS[section]
    contexte_bloc = f"\n\nContexte global du patient :\n{contexte.strip()}" if contexte.strip() else ""
    return (
        f"Section à rédiger : {titre}\n"
        f"Consigne : {consigne}"
        f"{contexte_bloc}\n\n"
        f"Notes cliniques brutes :\n---\n{notes.strip()}\n---\n\n"
        f"Rédige la section « {titre} » en français."
    )
