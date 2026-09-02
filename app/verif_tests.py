"""Traçabilité des noms de tests proposés par le LLM (garde-fou déterministe).

Constat de la revue du 2026-08-11, reproduit deux fois sur deux : une dictée
mentionnant « la dictée de la Batelem » ressortait en « EVALEO 6-15 » — un test
jamais dicté, que le modèle a pris dans la liste de tests usuels que le prompt
lui fournit lui-même (`prompts.py`). Le catalogue donné pour aider à la
*reconnaissance* sert de vocabulaire d'*invention*.

`verif_chiffres` n'y voyait que « 6 » et « -15 » — les chiffres du *nom* du
test : un signalement incompréhensible, et rien du tout pour un test dont le nom
ne comporte aucun chiffre. Attribuer un score au mauvais test est pourtant
l'erreur la plus lourde de toute la chaîne dans un document médico-légal.

Même doctrine que `verif_chiffres` : on signale, on ne corrige pas ; le
sur-signalement est bénin, le sous-signalement ne l'est pas.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from .verif_chiffres import _sans_accents

# En deçà, le nom n'est plus discriminant (« %SS » → « ss ») : le chercher
# produirait du bruit sans rien attraper d'utile.
_LONGUEUR_MIN = 3


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, ponctuation réduite à des espaces simples.

    « EVALEO 6-15 » et « evaleo 6/15 » doivent se comparer : les noms de tests
    s'écrivent avec des tirets, des barres et des parenthèses selon la source."""
    return re.sub(r"[^a-z0-9]+", " ", _sans_accents(texte.lower())).strip()


def variantes(nom: str) -> list[str]:
    """Formes normalisées sous lesquelles un test peut être cité.

    Un catalogue écrit « GRBAS / GIRBAS » (deux noms) ou « VHI (Voice Handicap
    Index) » (sigle + développement) : un compte-rendu, lui, n'en cite qu'une
    partie."""
    formes = [nom]
    formes += nom.split("/")                      # « GRBAS / GIRBAS »
    formes.append(re.sub(r"\(.*?\)", " ", nom))   # « VHI (…) » → « VHI »
    out: list[str] = []
    for f in formes:
        v = normaliser(f)
        if len(v.replace(" ", "")) >= _LONGUEUR_MIN and v not in out:
            out.append(v)
    return out


_MOT_DU_NOM = re.compile(r"[^\W_]+")


def nom_surveillable(nom: str) -> bool:
    """Le libellé du catalogue a-t-il l'aspect d'un nom de test ?

    Certaines entrées sont autant des tournures de compte-rendu que des noms
    d'épreuves (« Fluences verbales », « Analyse acoustique ») : les surveiller
    signalait une rédaction fidèle, et c'est le faux positif qui fait ignorer un
    garde-fou. Critère volontairement large — chiffre, trait d'union, sigle, ou
    mot unique — pour ne laisser sortir de la surveillance que les libellés
    entièrement composés de mots courants."""
    if any(c.isdigit() for c in nom) or "-" in nom:
        return True
    mots = _MOT_DU_NOM.findall(nom)
    if len(mots) <= 1:
        return True
    return any(len(m) >= 2 and m.isupper() for m in mots)


def _contient(texte_normalise: str, forme: str) -> bool:
    """Recherche bornée aux mots : « ELO » ne doit pas matcher « melon »."""
    return re.search(
        rf"(?<![a-z0-9]){re.escape(forme)}(?![a-z0-9])", texte_normalise
    ) is not None


def formes_source(nom: str) -> list[str]:
    """Formes admises pour reconnaître un test **dans la dictée**, plus
    tolérantes que celles cherchées dans le texte proposé.

    À l'oral, le numéro de version tombe : on dicte « l'Alouette » pour
    « Alouette-R », « l'ODEDYS » pour « ODEDYS-2 ». Un suffixe d'un seul
    caractère est donc facultatif côté source. La tolérance s'arrête là : une
    tranche d'âge (« EXALANG 8-11 » contre « EXALANG 3-6 ») distingue deux
    tests différents, et sa substitution doit rester visible."""
    formes = list(variantes(nom))
    for v in list(formes):
        segments = v.split()
        if len(segments) > 1 and len(segments[-1]) == 1:
            court = " ".join(segments[:-1])
            if len(court.replace(" ", "")) >= _LONGUEUR_MIN and court not in formes:
                formes.append(court)
    return formes


def tests_non_sources(
    propose: str, sources: Iterable[str], noms_connus: Iterable[str],
) -> list[str]:
    """Tests cités dans le texte proposé mais introuvables dans le matériau source.

    Un test est tenu pour dicté dès qu'une de ses formes apparaît dans la
    source : le praticien dicte « l'Alouette », le modèle écrit « Alouette-R »,
    et cette reconnaissance-là est exactement ce que l'outil doit permettre."""
    p = normaliser(propose)
    src = normaliser(" ".join(s or "" for s in sources))
    # Indexé par la forme effectivement lue dans le texte proposé : deux entrées
    # du catalogue peuvent recouvrir une seule citation (« EXALANG 3-6 » et
    # « EXALANG 3-6 (phono) »), et deux alertes pour le même mot rendent le
    # signalement illisible.
    manquants: dict[str, str] = {}
    for nom in noms_connus:
        if not nom_surveillable(nom):
            continue
        cite = next((f for f in variantes(nom) if _contient(p, f)), None)
        if cite is None:
            continue
        if any(_contient(src, f) for f in formes_source(nom)):
            continue
        # À citation égale, on nomme le test sous son libellé le plus court :
        # c'est celui que le praticien a sous les yeux dans le compte-rendu.
        retenu = manquants.get(cite)
        if retenu is None or len(normaliser(nom)) < len(normaliser(retenu)):
            manquants[cite] = nom
    return list(dict.fromkeys(manquants.values()))


def signalements(
    propose: str, sources: Iterable[str], noms_connus: Iterable[str],
) -> list[str]:
    """Message court prêt à afficher, nommant le test en cause."""
    manquants = tests_non_sources(propose, sources, noms_connus)
    if not manquants:
        return []
    return [
        "test(s) cité(s) mais absent(s) de votre dictée : " + ", ".join(manquants)
    ]
