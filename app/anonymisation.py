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
        # Comparaison sans accents : selon la source, le document écrit
        # « ÉPREUVES » ou « EPREUVES » pour la même rubrique.
        mots = [x for x in _SEPARATEUR_MOTS.split(_sans_accents(m.group(0)).upper()) if x]
        # Une lettre isolée n'identifie personne : c'est l'article élidé happé
        # par l'apostrophe (« L'ALOUETTE-R ») ou l'indice de version d'un test.
        porteurs = [mot for mot in mots if len(mot) > 1]
        if porteurs and all(mot in attendus for mot in porteurs):
            return m.group(0)
        # Un sigle isolé de 3-4 lettres est plus souvent clinique que nominatif.
        if len(mots) == 1 and len(mots[0]) <= 4:
            return m.group(0)
        return MARQUEUR_NOM

    return _CAPITALES.sub(remplacer, texte)


# Repérage des noms *avant* caviardage, pour pouvoir ensuite traquer leurs
# autres occurrences : « Patient : DURAND Léa » en en-tête apprend que « Léa »,
# citée dix lignes plus bas au fil du texte, est elle aussi un prénom.
_SOURCES_DE_NOMS = [
    re.compile(rf"\b{_CIVILITES}[ \t]+({_MOT_PROPRE}(?:[ \t]+{_MOT_PROPRE})?)"),
    re.compile(rf"\b(?i:{_ETIQUETTES})[ \t]*:[ \t]*"
               rf"({_MOT_PROPRE}(?:[ \t-]{_MOT_PROPRE})?)"),
]
# Mots qui suivent parfois une civilité ou une étiquette sans être des noms.
_PAS_DES_NOMS = {
    "Le", "La", "Les", "Un", "Une", "Des", "Son", "Sa", "Ses", "Cette", "Ce",
    "Madame", "Monsieur", "Docteur", "Orthophoniste", "Enfant", "Patient",
    "Patiente", "Bilan", "Anamnèse", "Anamnese", "Non", "Oui", "Fictif",
}


def noms_du_document(texte: str) -> set[str]:
    noms: set[str] = set()
    for motif in _SOURCES_DE_NOMS:
        for m in motif.finditer(texte):
            for mot in re.split(r"[\s-]+", m.group(1)):
                mot = mot.strip("'’-")
                # Ceinture et bretelles : un mot qui ne commence pas par une
                # majuscule n'est pas un nom, et le prendre pour tel le fait
                # remplacer partout ailleurs dans le document.
                if not mot[:1].isupper():
                    continue
                if len(mot) >= 3 and mot not in _PAS_DES_NOMS:
                    noms.add(mot)
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
