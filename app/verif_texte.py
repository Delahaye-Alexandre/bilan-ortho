"""Adossement d'une rubrique proposée au matériau réellement dicté.

Constat de la revue du 2026-08-11 : soumise à « euh, bonjour, je ne sais pas
trop quoi dire, il fait beau aujourd'hui », l'anamnèse produite décrivait une
plainte clinique complète (évitement des situations de parole, souffrance
associée). Aucun signalement : `verif_chiffres` ne voit que les nombres, et une
prose entièrement inventée n'en contient pas.

La mesure ici est volontairement grossière — part des termes significatifs du
texte proposé qui se retrouvent dans le matériau source — et son seuil est bas.
Reformuler est le travail attendu de l'outil : une rédaction fidèle réemploie
une partie du vocabulaire dicté, jamais sa totalité. On ne cherche donc pas à
mesurer la fidélité, mais à repérer le cas franc : une rubrique substantielle
qui ne doit presque rien à ce qui a été dit. Mieux vaut manquer une invention
partielle que noyer le praticien d'alertes — ce sont les faux positifs qui
ruinent un garde-fou.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from .verif_chiffres import _sans_accents

# Mots-outils : leur présence ne dit rien de l'origine du contenu.
_MOTS_OUTILS = {
    "avec", "sans", "dans", "pour", "vers", "chez", "cette", "celui", "leur",
    "leurs", "elle", "elles", "nous", "vous", "cela", "donc", "mais", "plus",
    "moins", "tres", "aussi", "meme", "entre", "apres", "avant", "lors",
    "lorsqu", "quand", "alors", "ainsi", "etre", "avoir", "fait", "faire",
    "peut", "doit", "sont", "etait", "ete", "cet", "ses", "son", "que", "qui",
}
# En deçà, une rubrique est trop courte pour qu'un recouvrement faible
# signifie quoi que ce soit (« Audition normale. »). Douze termes laissaient
# passer une plainte inventée de deux phrases (passe réelle du 2026-09-02).
LONGUEUR_MIN = 8
# Seuil délibérément bas : il ne doit se déclencher que sur le cas franc.
SEUIL = 0.2
# Le diagnostic et le projet thérapeutique sont, par nature, écrits dans le
# vocabulaire du clinicien plutôt que dans celui de la dictée (« trouble
# spécifique du langage écrit », « deux séances hebdomadaires ») : au seuil
# général, une conclusion parfaitement fondée était signalée une fois sur deux
# (passe réelle du 2026-09-02). Le garde-fou y reste, plus bas.
SEUIL_PAR_RUBRIQUE = {"diagnostic": 0.1, "projet": 0.1}
# Racine grossière : absorbe accords et flexions (« difficultés » /
# « difficulté », « langagières » / « langage »), sans lexique ni dépendance.
_RACINE = 6


def _termes(texte: str) -> list[str]:
    jetons = re.split(r"[^a-z0-9]+", _sans_accents(texte or "").lower())
    return [j for j in jetons if len(j) >= 4 and j not in _MOTS_OUTILS]


def adossement(propose: str, sources: Iterable[str]) -> float | None:
    """Part des termes du texte proposé retrouvés dans les sources.

    None quand le texte est trop court pour être jugé."""
    termes = _termes(propose)
    if len(termes) < LONGUEUR_MIN:
        return None
    connus = {t[:_RACINE] for s in sources for t in _termes(s or "")}
    retrouves = sum(1 for t in termes if t[:_RACINE] in connus)
    return retrouves / len(termes)


def seuil_pour(rubrique: str | None) -> float:
    """Seuil d'alerte applicable à une rubrique (clé de la trame)."""
    return SEUIL_PAR_RUBRIQUE.get(rubrique or "", SEUIL)


def signalements(
    propose: str, sources: Iterable[str], rubrique: str | None = None
) -> list[str]:
    """Message court prêt à afficher quand la rubrique n'est presque pas adossée."""
    part = adossement(propose, sources)
    if part is None or part >= seuil_pour(rubrique):
        return []
    return [
        f"rubrique très peu adossée à votre dictée ({round(part * 100)} % de ses "
        "termes s'y retrouvent) : vérifiez qu'elle n'affirme rien que vous "
        "n'ayez dit"
    ]
