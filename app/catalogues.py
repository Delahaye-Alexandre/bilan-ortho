"""Catalogues cliniques par domaine : orientations de rédaction + tests étalonnés.

Données issues de la recherche (`docs/recherche-bilan-ortho.md`). Éditable et
extensible (Phase 5 : édition depuis l'UI). Sert à : (1) orienter la structuration
IA (tests connus par domaine), (2) proposer des tests dans la saisie structurée.

Métriques : ecart_type | percentile | note_standard | note_standard_100 | age_dev
| age_lecture | qualitatif

Les deux échelles de notes standard sont distinguées : `note_standard` = moyenne
10 / ET 3 (batteries françaises), `note_standard_100` = moyenne 100 / ET 15
(Vineland…). Les confondre fausse le drapeau de sévérité (cf. bilan.py).
"""
from __future__ import annotations

GENERIC_GUIDANCE = (
    "Décrire les épreuves administrées et leurs résultats. Toujours accompagner "
    "un score de son étalonnage (écart-type, percentile, note standard ou âge de "
    "développement) et de son interprétation. Ne jamais présenter un score brut seul."
)

CATALOGUES: dict[str, dict] = {
    "langage_oral": {
        "guidance": "Explorer versants réceptif et expressif : articulation, phonologie, "
        "lexique (réception/production), morphosyntaxe, pragmatique, fluence.",
        "tests": [
            {"nom": "EVALO 2-6", "tranche": "2;6-6;3", "mesure": "langage oral global", "metriques": ["ecart_type", "percentile"]},
            {"nom": "N-EEL", "tranche": "3;7-8;7", "mesure": "compréhension, expression, phonologie, vocabulaire", "metriques": ["ecart_type", "percentile"]},
            {"nom": "ELO", "tranche": "3-11 ans", "mesure": "lexique & morphosyntaxe (réception/production)", "metriques": ["ecart_type", "percentile", "age_dev"]},
            {"nom": "EXALANG 3-6", "tranche": "3-6 ans", "mesure": "langage oral (informatisé)", "metriques": ["ecart_type", "percentile", "note_standard"]},
            {"nom": "EVIP", "tranche": "≥ 2;6", "mesure": "vocabulaire réceptif", "metriques": ["ecart_type", "percentile", "age_dev"]},
            {"nom": "ECOSSE", "tranche": "enfant", "mesure": "compréhension syntaxique", "metriques": ["percentile", "ecart_type"]},
        ],
    },
    "langage_ecrit": {
        "guidance": "Explorer : lecture (identification de mots — voies d'assemblage/adressage —, "
        "compréhension écrite), transcription/orthographe (lexicale et grammaticale), conscience "
        "phonologique, mémoire de travail, traitement visuo-attentionnel. Comparer à la norme d'âge "
        "ET au niveau scolaire.",
        "tests": [
            {"nom": "Alouette-R", "tranche": "≥ CP", "mesure": "vitesse + précision de lecture", "metriques": ["age_lecture", "percentile"]},
            {"nom": "EVALEO 6-15", "tranche": "6-15 ans", "mesure": "langage oral ET écrit", "metriques": ["ecart_type", "percentile", "note_standard"]},
            {"nom": "EXALANG 8-11", "tranche": "8-11 ans", "mesure": "langage écrit, mémoire, attention", "metriques": ["ecart_type", "percentile", "note_standard"]},
            {"nom": "ODEDYS-2", "tranche": "CE1-5e", "mesure": "dépistage lecture/orthographe", "metriques": ["percentile", "ecart_type"]},
            {"nom": "BALE", "tranche": "primaire", "mesure": "lecture mots/pseudo-mots, dictée, copie", "metriques": ["ecart_type", "percentile"]},
            {"nom": "ELFE", "tranche": "CE1-6e", "mesure": "fluence de lecture (mots/min)", "metriques": ["percentile"]},
            {"nom": "Chronodictées", "tranche": "primaire-collège", "mesure": "orthographe étalonnée", "metriques": ["ecart_type", "percentile"]},
        ],
    },
    "parole_articulation": {
        "guidance": "Analyser l'articulation, la phonologie (processus phonologiques), les praxies "
        "bucco-faciales, la répétition de logatomes (programmation phonologique).",
        "tests": [
            {"nom": "BEPL", "tranche": "jeune enfant", "mesure": "inventaire phonémique, structures syllabiques", "metriques": ["ecart_type", "qualitatif"]},
            {"nom": "EXALANG 3-6 (phono)", "tranche": "3-6 ans", "mesure": "phonologie", "metriques": ["ecart_type", "percentile"]},
            {"nom": "MBLF", "tranche": "tous", "mesure": "motricité bucco-linguo-faciale, praxies", "metriques": ["qualitatif"]},
        ],
    },
    "cognition_mathematique": {
        "guidance": "Explorer dénombrement, transcodage, calcul mental/posé, résolution de problèmes, "
        "construction du nombre, cognition mathématique.",
        "tests": [
            {"nom": "TEDI-MATH", "tranche": "GS-CE2", "mesure": "dénombrement, transcodage, calcul, logique", "metriques": ["ecart_type", "percentile"]},
            {"nom": "TEDI-MATH Grands", "tranche": "CE2-5e", "mesure": "cognition math (grands)", "metriques": ["ecart_type", "percentile"]},
            {"nom": "ZAREKI-R", "tranche": "primaire", "mesure": "comptage, calcul, transcodage, problèmes", "metriques": ["ecart_type", "percentile"]},
            {"nom": "EXAMATH 8-15", "tranche": "8-15 ans", "mesure": "cognition mathématique (informatisé)", "metriques": ["ecart_type", "percentile", "note_standard"]},
            {"nom": "UDN-II", "tranche": "enfant", "mesure": "construction du nombre (Piaget)", "metriques": ["age_dev", "qualitatif"]},
        ],
    },
    "voix": {
        "guidance": "Anamnèse vocale, analyse perceptive (GRBAS), auto-évaluation du handicap (VHI), "
        "paramètres acoustiques (F0, jitter, shimmer), temps maximal de phonation, comportement vocal.",
        "tests": [
            {"nom": "GRBAS / GIRBAS", "tranche": "tous", "mesure": "évaluation perceptive de la voix (0-3)", "metriques": ["qualitatif"]},
            {"nom": "VHI (Voice Handicap Index)", "tranche": "adulte", "mesure": "auto-évaluation du handicap vocal", "metriques": ["qualitatif"]},
            {"nom": "CAPE-V", "tranche": "tous", "mesure": "évaluation perceptive standardisée", "metriques": ["qualitatif"]},
            {"nom": "Analyse acoustique", "tranche": "tous", "mesure": "F0, jitter, shimmer, TMP", "metriques": ["qualitatif"]},
        ],
    },
    "deglutition_omf": {
        "guidance": "Évaluer praxies oro-faciales, phases de la déglutition, essais texturés, "
        "ventilation, fausses routes ; retentissement (EAT-10, DHI).",
        "tests": [
            {"nom": "MBLF", "tranche": "tous", "mesure": "motricité bucco-linguo-faciale", "metriques": ["qualitatif"]},
            {"nom": "EAT-10", "tranche": "adulte", "mesure": "dépistage dysphagie (auto-questionnaire)", "metriques": ["qualitatif"]},
            {"nom": "DHI", "tranche": "adulte", "mesure": "handicap de déglutition", "metriques": ["qualitatif"]},
        ],
    },
    "neuro_acquise": {
        "guidance": "Aphasie/dysarthrie/neurodégénératif : production et compréhension orales/écrites, "
        "dénomination, répétition, mémoire/cognition, communication fonctionnelle, retentissement sur "
        "l'autonomie. Anamnèse orientée pathologie (AVC, TC, maladie neurodégénérative) et entourage.",
        "tests": [
            {"nom": "MT-86", "tranche": "adulte", "mesure": "batterie clinique d'aphasie", "metriques": ["qualitatif", "percentile"]},
            {"nom": "BDAE", "tranche": "adulte", "mesure": "classification des aphasies", "metriques": ["qualitatif"]},
            {"nom": "BIA", "tranche": "≥ 15 ans", "mesure": "6 domaines langagiers (informatisé)", "metriques": ["qualitatif"]},
            {"nom": "GRÉMOTS", "tranche": "adulte", "mesure": "langage (neurodégénératif)", "metriques": ["ecart_type", "percentile"]},
            {"nom": "DO 80", "tranche": "ado/adulte", "mesure": "dénomination orale (80 images)", "metriques": ["percentile"]},
            {"nom": "Fluences verbales", "tranche": "adulte", "mesure": "accès lexical (P / animaux)", "metriques": ["ecart_type", "percentile"]},
        ],
    },
    "begaiement": {
        "guidance": "Types et fréquence des disfluences (%SS), tensions/concomitances, sévérité, "
        "retentissement et vécu.",
        "tests": [
            {"nom": "%SS", "tranche": "tous", "mesure": "pourcentage de syllabes bégayées", "metriques": ["qualitatif"]},
            {"nom": "SSI-4", "tranche": "tous", "mesure": "sévérité du bégaiement", "metriques": ["percentile", "qualitatif"]},
            {"nom": "OASES", "tranche": "tous", "mesure": "impact / vécu", "metriques": ["qualitatif"]},
        ],
    },
    "communication_tsa": {
        "guidance": "Communication sociale et pragmatique, communication fonctionnelle, CAA, "
        "comportements adaptatifs ; évaluation majoritairement qualitative/écologique + questionnaires.",
        "tests": [
            {"nom": "ECSP", "tranche": "jeune enfant", "mesure": "communication sociale précoce", "metriques": ["qualitatif"]},
            {"nom": "CCC-2", "tranche": "enfant", "mesure": "pragmatique (questionnaire)", "metriques": ["qualitatif"]},
            {"nom": "Vineland", "tranche": "tous", "mesure": "comportements adaptatifs", "metriques": ["note_standard_100", "qualitatif"]},
        ],
    },
    "surdite": {
        "guidance": "Langage oral/écrit adaptés (avec/sans lecture labiale), perception de la parole "
        "(listes cochléaires, mots/phrases), suivi post-implant (% de reconnaissance).",
        "tests": [
            {"nom": "Épreuves de perception de la parole", "tranche": "tous", "mesure": "% de reconnaissance", "metriques": ["qualitatif"]},
        ],
    },
    "oralite_nourrisson": {
        "guidance": "Oralité alimentaire : grilles d'observation d'un repas, questionnaires parentaux "
        "(textures, sélectivité, réflexe nauséeux, parcours nutrition entérale). Évaluation surtout "
        "qualitative — privilégier items + texte libre plutôt que scores.",
        "tests": [
            {"nom": "Grille d'observation du repas", "tranche": "0-6 ans", "mesure": "oralité alimentaire", "metriques": ["qualitatif"]},
            {"nom": "Questionnaire parental d'oralité", "tranche": "0-6 ans", "mesure": "habitudes, sélectivité", "metriques": ["qualitatif"]},
        ],
    },
}


def get(cle: str, cfg: dict | None = None) -> dict:
    """Catalogue d'un domaine, surcharges praticien (config `catalogues`)
    appliquées champ par champ (guidance et/ou tests)."""
    base = CATALOGUES.get(cle, {"guidance": GENERIC_GUIDANCE, "tests": []})
    override = ((cfg or {}).get("catalogues") or {}).get(cle)
    if not isinstance(override, dict):
        return base
    out = dict(base)
    if isinstance(override.get("guidance"), str):
        out["guidance"] = override["guidance"]
    if isinstance(override.get("tests"), list):
        out["tests"] = [t for t in override["tests"] if isinstance(t, dict) and t.get("nom")]
    return out


def tests_noms(domaines: list[str], cfg: dict | None = None) -> list[str]:
    noms: list[str] = []
    for c in domaines:
        for t in get(c, cfg).get("tests", []):
            if t["nom"] not in noms:
                noms.append(t["nom"])
    return noms


def tous_les_noms(cfg: dict | None = None) -> list[str]:
    """Tous les noms de tests connus, domaines intégrés et surcharges comprises.

    Sert au garde-fou anti-substitution (`verif_tests`) : ce sont les noms que
    le modèle a sous les yeux dans son prompt, donc ceux qu'il peut citer — y
    compris hors du domaine du bilan en cours."""
    from . import config

    cles = [d["cle"] for d in config.DOMAINES]
    for c in ((cfg or {}).get("catalogues") or {}):
        if c not in cles:
            cles.append(c)
    return tests_noms(cles, cfg)


def guidance(domaines: list[str], cfg: dict | None = None) -> str:
    parts = [get(c, cfg).get("guidance", "") for c in domaines if get(c, cfg).get("guidance")]
    return " ".join(parts) if parts else GENERIC_GUIDANCE
