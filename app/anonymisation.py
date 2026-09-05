"""Pseudonymisation des bilans importés comme références de style.

Les bilans que le praticien importe pour transmettre SON style sont de vrais
comptes-rendus, avec de vrais patients. Ils sont ensuite réinjectés — par
proximité sémantique — dans le prompt d'autres dossiers : l'extrait retenu est
celui du patient *le plus ressemblant* au dossier en cours. Sans traitement, un
bloc d'identité (nom, date de naissance, adresse, prescripteur) pouvait donc se
retrouver sous les yeux du modèle pendant la rédaction du bilan d'un autre.

Ce module caviarde ce qui est repérable de façon déterministe : identifiants,
coordonnées, dates, adresses, et les noms propres introduits par une civilité
ou une étiquette. Les scores et étalonnages sont **conservés** : ils font partie
du style de restitution, et tout chiffre non dicté est de toute façon signalé au
praticien par `verif_chiffres`.

Aucune détection de noms propres n'est complète sans modèle linguistique : le
caviardage réduit le risque, il ne l'annule pas. C'est pourquoi l'interface le
dit au moment de l'import, plutôt que de laisser croire à une garantie.
"""
from __future__ import annotations

import re

from .verif_chiffres import _sans_accents

MARQUEUR_NOM = "[NOM]"
MARQUEUR_DATE = "[DATE]"

_MOIS = (
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|"
    "octobre|novembre|décembre|decembre"
)
_CIVILITES = r"(?:M\.|Mme|Mlle|Mr|Dr|Docteur|Pr|Professeur|Monsieur|Madame|Mademoiselle)"
# Étiquettes de champ d'un en-tête de compte-rendu.
_ETIQUETTES = (
    r"(?:nom|prénom|prenom|patient|patiente|enfant|prescripteur|médecin|medecin|"
    r"adressé par|adresse par|nom de naissance)"
)
_MOT_PROPRE = r"[A-ZÀ-Ý][\w'’\-]+"
# Ce qui peut légitimement suivre « né le » / « née en » : un marqueur déjà
# posé par les règles précédentes, ou une date encore en clair. Volontairement
# borné — c'est en avalant n'importe quel mot suivant (`\S+`) que la règle
# détruisait les phrases.
_APRES_NAISSANCE = (
    rf"(?:{re.escape(MARQUEUR_DATE)}"
    rf"|\d[\w/-]*(?:[ \t]+(?:{_MOIS}))?(?:[ \t]+\d{{2,4}})?"
    rf"|(?:{_MOIS})[ \t]+\d{{2,4}})"
)

# (motif, remplacement) — l'ordre compte : les identifiants d'abord, les noms
# ensuite (une civilité peut précéder une adresse).
_REGLES: list[tuple[re.Pattern[str], str]] = [
    # Numéro de sécurité sociale (avec ou sans clé, espacé ou non).
    (re.compile(r"\b[12][\s.]?\d{2}[\s.]?\d{2}[\s.]?\d{2,3}[\s.]?\d{3}[\s.]?\d{3}"
                r"(?:[\s.]?\d{2})?\b"), "[NIR]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b"), "[COURRIEL]"),
    (re.compile(r"\b0\s?\d(?:[\s.-]?\d{2}){4}\b"), "[TÉL]"),
    # RPPS / ADELI explicites (9 chiffres) : identifiants nominatifs.
    (re.compile(r"\b(RPPS|ADELI|N°\s?ADELI)\s*:?\s*\d{6,15}\b", re.I), r"\1 [ID]"),
    (re.compile(rf"\b\d{{1,2}}\s+(?:{_MOIS})\s+\d{{4}}\b", re.I), MARQUEUR_DATE),
    (re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"), MARQUEUR_DATE),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), MARQUEUR_DATE),
    # Adresse postale : numéro + type de voie + libellé.
    (re.compile(r"\b\d{1,4}(?:\s?(?:bis|ter))?,?\s+(?:rue|avenue|av\.|boulevard|bd\.?|"
                r"impasse|allée|allee|chemin|place|route|résidence|residence)\s+"
                r"[^\n,;.]{2,40}", re.I), "[ADRESSE]"),
    # Code postal + commune.
    (re.compile(rf"\b\d{{5}}[ \t]+{_MOT_PROPRE}(?:[ \t-]{_MOT_PROPRE})?\b"), "[ADRESSE]"),
    # « Mme Durand », « Dr Bernard-Martin ».
    (re.compile(rf"\b{_CIVILITES}[ \t]+{_MOT_PROPRE}(?:[ \t]+{_MOT_PROPRE})?"), MARQUEUR_NOM),
    # « Nom : DURAND », « Patient : Léa Durand », « adressé par Dr … ».
    # `re.I` ne porte que sur l'étiquette : appliqué à tout le motif, il rendait
    # `_MOT_PROPRE` insensible à la casse, si bien que « Enfant : scolarisée en
    # CE2 » caviardait « scolarisée » — puis la pourchassait comme patronyme
    # dans tout le document (cf. `noms_du_document`).
    (re.compile(rf"\b((?i:{_ETIQUETTES}))[ \t]*:[ \t]*{_MOT_PROPRE}"
                rf"(?:[ \t-]{_MOT_PROPRE})?"),
     r"\1 : " + MARQUEUR_NOM),
    # « né le … », « née en … » : le participe reste tel qu'il est écrit,
    # l'information part. Le « e » accentué (ou doublé) est exigé : avec
    # `n[ée]e?` et `re.I`, « ne le » — « il ne le fait pas » — était réécrit en
    # date de naissance et le mot suivant supprimé, dans un texte destiné à
    # être relu par le modèle comme exemple du style du praticien.
    (re.compile(rf"\b(n(?:ée?|ee)[ \t]+(?:le|en)[ \t]+){_APRES_NAISSANCE}", re.I),
     r"\1" + MARQUEUR_DATE),
]

# Suites de capitales : un nom de famille s'écrit souvent « DURAND » dans un
# en-tête. Les titres de rubriques aussi — d'où la liste d'exceptions.
_CAPITALES = re.compile(r"\b[A-ZÀ-Ý][A-ZÀ-Ý'’-]{2,}(?:[ \t]+[A-ZÀ-Ý][A-ZÀ-Ý'’-]{2,})*\b")
_CAPITALES_ATTENDUES = {
    # Libellés des marqueurs déjà posés : sans eux, « [ADRESSE] » deviendrait
    # « [[NOM]] » à la passe suivante.
    "NOM", "DATE", "TÉL", "TEL", "NIR", "ID", "ADRESSE", "COURRIEL",
    "ANAMNESE", "ANAMNÈSE", "BILAN", "COMPTE", "RENDU", "CONCLUSION", "DIAGNOSTIC",
    "OBSERVATIONS", "EPREUVES", "ÉPREUVES", "RESULTATS", "RÉSULTATS", "SYNTHESE",
    "SYNTHÈSE", "PROJET", "THERAPEUTIQUE", "THÉRAPEUTIQUE", "ADMINISTRATIF",
    "ORTHOPHONIQUE", "ORTHOPHONISTE", "DOCUMENT", "FICTIF", "OBJET", "MOTIF",
    "TESTS", "SCORES", "NGAP", "AMO", "RPPS", "ADELI", "SIRET", "ET", "NS",
    "CP", "CE1", "CE2", "CM1", "CM2", "GS", "MS", "PS", "QI", "TDA", "TDAH", "TSA",
    "AVC", "ORL", "IRM", "MDPH", "SESSAD", "CMPP", "CAMSP", "ULIS", "SEGPA",
    # Titres de rubriques et vocabulaire clinique qu'un compte-rendu écrit en
    # capitales : ils partaient en [NOM] dès qu'ils sortaient de la liste
    # ci-dessus (passe réelle du 2026-09-02). Un titre caviardé n'est pas une
    # fuite, mais l'extrait perd sa structure — ce qu'il doit transmettre.
    # Aucun de ces mots n'est un patronyme courant.
    "ANTECEDENTS", "ANTÉCÉDENTS", "MEDICAUX", "MÉDICAUX", "FAMILIAUX", "PERSONNELS",
    "PLAINTE", "DEMANDE", "ATTENTES", "CONTEXTE", "HISTOIRE", "PARCOURS", "SCOLAIRE",
    "SCOLARITE", "SCOLARITÉ", "PROFESSIONNEL", "DEVELOPPEMENT", "DÉVELOPPEMENT",
    "PSYCHOMOTEUR", "LANGAGE", "ORAL", "ECRIT", "ÉCRIT", "LECTURE", "ORTHOGRAPHE",
    "ECRITURE", "ÉCRITURE", "GRAPHISME", "COMPREHENSION", "COMPRÉHENSION", "EXPRESSION",
    "PRODUCTION", "RECEPTION", "RÉCEPTION", "PHONOLOGIE", "PHONOLOGIQUE", "ARTICULATION",
    "PAROLE", "LEXIQUE", "LEXICAL", "SEMANTIQUE", "SÉMANTIQUE", "MORPHOSYNTAXE", "SYNTAXE",
    "PRAGMATIQUE", "DISCOURS", "RECIT", "RÉCIT", "MEMOIRE", "MÉMOIRE", "ATTENTION",
    "FONCTIONS", "EXECUTIVES", "EXÉCUTIVES", "COGNITION", "MATHEMATIQUE", "MATHÉMATIQUE",
    "MATHEMATIQUES", "MATHÉMATIQUES", "NOMBRE", "NUMERATION", "NUMÉRATION", "CALCUL",
    "RESOLUTION", "RÉSOLUTION", "PROBLEMES", "PROBLÈMES", "LOGIQUE", "RAISONNEMENT",
    "VOIX", "DEGLUTITION", "DÉGLUTITION", "ORALITE", "ORALITÉ", "FLUENCE", "BEGAIEMENT",
    "BÉGAIEMENT", "COMMUNICATION", "AUDITION", "SURDITE", "SURDITÉ", "VISION",
    "EVALUATION", "ÉVALUATION", "EXAMEN", "PASSATION", "ANALYSE", "INTERPRETATION",
    "INTERPRÉTATION", "HYPOTHESE", "HYPOTHÈSE", "HYPOTHESES", "HYPOTHÈSES", "RESUME",
    "RÉSUMÉ", "PRECONISATIONS", "PRÉCONISATIONS", "RECOMMANDATIONS", "ORIENTATION",
    "PROPOSITION", "PROPOSITIONS", "OBJECTIFS", "AXES", "MOYENS", "PRISE", "CHARGE",
    "REEDUCATION", "RÉÉDUCATION", "SOINS", "SEANCES", "SÉANCES", "FREQUENCE", "FRÉQUENCE",
    "DUREE", "DURÉE", "SUIVI", "TRAITEMENT", "PRONOSTIC", "CONCLUSIONS", "COMPORTEMENT",
    "RELATION", "OBSERVATION", "REMARQUE", "REMARQUES", "COMMENTAIRE", "COMMENTAIRES", "SIGNATURE", "CACHET",
    "LIEU", "ORTHOPHONIE", "CABINET", "RENOUVELLEMENT", "INITIAL", "TABLEAU", "SCORE",
    "NOTE", "PERCENTILE", "ECART", "ÉCART", "TYPE", "MOYENNE", "NORME", "PATHOLOGIQUE",
    "DEFICITAIRE", "DÉFICITAIRE", "FRAGILE", "RESULTAT", "RÉSULTAT", "TOTAL", "PARTIE",
    "VOLET", "ANNEXE", "ANNEXES", "COLLEGE", "COLLÈGE", "LYCEE", "LYCÉE", "MATERNELLE",
    "PRIMAIRE", "ELEMENTAIRE", "ÉLÉMENTAIRE", "RASED", "PAI", "PAP", "PPS", "PPRE", "AVS",
    "AESH", "ITEP", "IME", "CMP", "CRTLA", "TSLO", "TSLE", "TDL", "TSLA", "DYS",
    "DYSLEXIE", "DYSORTHOGRAPHIE", "DYSPHASIE", "DYSCALCULIE", "DYSPRAXIE", "TROUBLE",
    "TROUBLES", "SPECIFIQUE", "SPÉCIFIQUE", "SPECIFIQUES", "SPÉCIFIQUES", "APPRENTISSAGES",
    "DEVELOPPEMENTAL", "DÉVELOPPEMENTAL", "RETARD", "DIFFICULTES", "DIFFICULTÉS", "POINTS",
    "FORTS", "FAIBLES", "FORCES", "FAIBLESSES", "ELEMENTS", "ÉLÉMENTS", "CLINIQUES", "AVIS",
    "ACCORD", "PARENTS", "FAMILLE", "MERE", "MÈRE", "PERE", "PÈRE", "ENFANT", "PATIENT",
    "PATIENTE", "ADULTE", "AGE", "ÂGE", "SEXE", "NAISSANCE", "CLASSE", "ECOLE", "ÉCOLE",
    "ENSEIGNANT", "ENSEIGNANTE", "MEDECIN", "MÉDECIN", "PRESCRIPTEUR", "PRESCRIPTION",
    "ORDONNANCE", "ADRESSEE", "ADRESSÉE", "NEUROLOGUE", "PEDIATRE", "PÉDIATRE",
    "PSYCHOLOGUE", "PSYCHOMOTRICIEN", "PSYCHOMOTRICIENNE", "ERGOTHERAPEUTE",
    "ERGOTHÉRAPEUTE", "ORTHOPTISTE", "PRENOM", "PRÉNOM", "TELEPHONE", "TÉLÉPHONE",
    "IDENTITE", "IDENTITÉ", "DONNEES", "DONNÉES", "ADMINISTRATIVES", "GENERALES",
    "GÉNÉRALES", "AUTRES", "DIVERS", "NEANT", "NÉANT", "AUCUN", "AUCUNE", "RAS",
    # Mots-outils de trois lettres et plus, qui coupent sinon une suite de
    # capitales par ailleurs légitime (« COMPTE RENDU DES ÉPREUVES »).
    "DES", "LES", "PAR", "SUR", "POUR", "AVEC", "SANS", "DANS", "AUX", "UNE", "SES",
}


# Une suite de capitales se découpe sur les espaces ET les traits d'union :
# testé d'un seul bloc, « COMPTE-RENDU » n'était reconnu ni comme « COMPTE »
# ni comme « RENDU », et le titre du document partait en [NOM].
_SEPARATEUR_MOTS = re.compile(r"[^A-Z0-9]+")


def _mots_attendus() -> set[str]:
    """Mots qu'une suite de capitales peut légitimement contenir.

    Aux libellés de rubriques s'ajoutent les noms de tests du catalogue : un
    compte-rendu écrit « L'ALOUETTE-R » ou « EXALANG », et c'est justement ce
    que l'extrait a vocation à transmettre — les caviarder revenait à retirer
    du corpus de style ce qui en fait la valeur clinique.

    Import tardif : `catalogues` remonte à `config`, que ce module n'a aucune
    raison de charger au moment de son propre import."""
    from . import catalogues

    attendus = {_sans_accents(m).upper() for m in _CAPITALES_ATTENDUES}
    for nom in catalogues.tous_les_noms():
        attendus.update(
            m for m in _SEPARATEUR_MOTS.split(_sans_accents(nom).upper()) if m
        )
    return attendus


def _caviarder_capitales(texte: str) -> str:
    attendus = _mots_attendus()

    def remplacer(m: re.Match[str]) -> str:
        if not _capitales_sont_un_nom(m.group(0), attendus):
            return m.group(0)
        # Jusqu'au deux-points sur la même ligne, rien que des capitales
        # (« HORAIRES : », « REMARQUE DE L'ENSEIGNANTE : ») : c'est l'étiquette
        # d'un champ, pas un nom — celui qui la suit a déjà été traité par les
        # règles d'étiquette.
        if _ETIQUETTE_EN_CAPITALES.match(m.string, m.end()):
            return m.group(0)
        return MARQUEUR_NOM

    return _CAPITALES.sub(remplacer, texte)


# Ce qui peut séparer une suite de capitales du deux-points de son étiquette :
# d'autres mots en capitales (dont les mots de deux lettres qui ont coupé la
# suite : « DE », « DU ») et des espaces.
_ETIQUETTE_EN_CAPITALES = re.compile(r"[ \t]*(?:[A-ZÀ-Ý0-9'’-]+[ \t]+)*:")


def _capitales_sont_un_nom(
    suite: str, attendus: set[str], exempter_sigles: bool = True
) -> bool:
    """Vrai si une suite de capitales ne s'explique par aucun titre, sigle ou
    nom de test connu — c'est alors très probablement un patronyme.

    Comparaison sans accents : selon la source, le document écrit « ÉPREUVES »
    ou « EPREUVES » pour la même rubrique. Une lettre isolée n'identifie
    personne (article élidé de « L'ALOUETTE-R », indice de version d'un test).
    Un sigle isolé de 3-4 lettres est plus souvent clinique que nominatif —
    sauf accolé à un prénom sur une ligne d'identité (``exempter_sigles``
    faux) : « ROUX Paul » est un nom."""
    mots = [x for x in _SEPARATEUR_MOTS.split(_sans_accents(suite).upper()) if x]
    porteurs = [mot for mot in mots if len(mot) > 1]
    if not porteurs or all(mot in attendus for mot in porteurs):
        return False
    if exempter_sigles and len(mots) == 1 and len(mots[0]) <= 4:
        return False
    return True


# Repérage des noms *avant* caviardage, pour pouvoir ensuite traquer leurs
# autres occurrences : « Patient : DURAND Léa » en en-tête apprend que « Léa »,
# citée dix lignes plus bas au fil du texte, est elle aussi un prénom.
_SOURCES_DE_NOMS = [
    re.compile(rf"\b{_CIVILITES}[ \t]+({_MOT_PROPRE}(?:[ \t]+{_MOT_PROPRE})?)"),
    re.compile(rf"\b(?i:{_ETIQUETTES})[ \t]*:[ \t]*"
               rf"({_MOT_PROPRE}(?:[ \t-]{_MOT_PROPRE})?)"),
]
# « DURAND Léa » ou « Léa DURAND » sur une ligne courte d'en-tête, sans
# civilité ni étiquette : le patronyme en capitales partait bien (suite de
# capitales), mais le prénom en casse mixte n'était relevé nulle part et
# restait en clair dans tout le corps du texte (passe réelle du 2026-09-02).
_PATRONYME_CAPITALES = r"[A-ZÀ-Ý][A-ZÀ-Ý'’-]{2,}"
_PRENOM_MIXTE = r"[A-ZÀ-Ý][a-zà-ÿ][\w'’-]*"
_NOM_ET_PRENOM = [
    re.compile(rf"(?<![\w'’-])({_PATRONYME_CAPITALES})[ \t]+({_PRENOM_MIXTE})\b"),
    re.compile(rf"\b({_PRENOM_MIXTE})[ \t]+({_PATRONYME_CAPITALES})(?![\w'’-])"),
]
# Au-delà, la ligne est de la prose (un titre suivi de son texte), pas une
# ligne d'identité.
_LIGNE_IDENTITE_MOTS_MAX = 8

# Mots qui suivent parfois une civilité ou une étiquette sans être des noms.
_PAS_DES_NOMS = {
    "Le", "La", "Les", "Un", "Une", "Des", "Son", "Sa", "Ses", "Cette", "Ce",
    "Madame", "Monsieur", "Docteur", "Orthophoniste", "Enfant", "Patient",
    "Patiente", "Bilan", "Anamnèse", "Anamnese", "Non", "Oui", "Fictif",
    # Voisins fréquents d'un titre en capitales sur une ligne courte.
    "Aucun", "Aucune", "Pas", "Rien", "Voir", "Néant", "Neant", "Sans", "Avec",
    "Normal", "Normale", "Date", "Nom", "Prénom", "Prenom", "Adresse", "Age", "Âge",
    "Classe", "École", "Ecole", "Motif", "Objet", "Suite", "Fait", "Note", "Notes",
}


def _retenir_nom(noms: set[str], mot: str) -> None:
    mot = mot.strip("'’-")
    # Ceinture et bretelles : un mot qui ne commence pas par une majuscule
    # n'est pas un nom, et le prendre pour tel le fait remplacer partout
    # ailleurs dans le document.
    if mot[:1].isupper() and len(mot) >= 3 and mot not in _PAS_DES_NOMS:
        noms.add(mot)


def noms_du_document(texte: str) -> set[str]:
    noms: set[str] = set()
    for motif in _SOURCES_DE_NOMS:
        for m in motif.finditer(texte):
            for mot in re.split(r"[\s-]+", m.group(1)):
                _retenir_nom(noms, mot)
    attendus = None
    for ligne in texte.splitlines():
        if len(ligne.split()) > _LIGNE_IDENTITE_MOTS_MAX:
            continue
        for motif in _NOM_ET_PRENOM:
            for m in motif.finditer(ligne):
                a, b = m.group(1), m.group(2)
                capitales, mixte = (a, b) if a.isupper() else (b, a)
                if attendus is None:
                    attendus = _mots_attendus()
                if not _capitales_sont_un_nom(capitales, attendus, exempter_sigles=False):
                    continue
                _retenir_nom(noms, capitales)
                _retenir_nom(noms, mixte)
    return noms


def caviarder(texte: str, noms_connus: set[str] | None = None) -> tuple[str, int]:
    """Retourne (texte pseudonymisé, nombre d'éléments remplacés).

    ``noms_connus`` porte les noms relevés ailleurs dans le même document :
    l'identité figure dans l'en-tête, et c'est le corps du texte — traité
    séparément, une fois l'en-tête écarté — qui la répète au fil des phrases."""
    out = texte
    total = 0
    noms = noms_du_document(texte) | (noms_connus or set())
    for motif, remplacement in _REGLES:
        out, n = motif.subn(remplacement, out)
        total += n
    # Autres occurrences des noms repérés en en-tête, au fil du texte.
    for nom in sorted(noms, key=len, reverse=True):
        out, n = re.subn(rf"\b{re.escape(nom)}\b", MARQUEUR_NOM, out)
        total += n
    avant = out.count(MARQUEUR_NOM)
    out = _caviarder_capitales(out)
    total += out.count(MARQUEUR_NOM) - avant
    return out, total
