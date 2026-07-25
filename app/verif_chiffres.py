"""Traçabilité des chiffres proposés par le LLM (garde-fou déterministe).

« L'IA n'invente aucun score » est la promesse centrale du produit et la
condition de son usage médico-légal. Une consigne de prompt ne suffit pas : un
modèle local de 4 milliards de paramètres produit malgré tout des étalonnages
plausibles mais absents de la dictée (percentiles déduits d'écarts-types,
résultat d'un test attribué à un autre).

Ce module ne fait donc **aucune** confiance au modèle : il vérifie que chaque
nombre du texte proposé se retrouve dans le matériau source (dictée, réponses
du praticien, contenu déjà rédigé), et signale les autres au praticien.

Deux principes tiennent tout le module :

- **On signale, on ne corrige pas.** Supprimer d'office un chiffre reviendrait
  à altérer un document clinique sur la foi d'une heuristique. Le praticien
  relit et tranche ; l'outil se contente de pointer.
- **Le sur-signalement est bénin, le sous-signalement ne l'est pas.** Un faux
  positif coûte un coup d'œil ; un score inventé qui passe inaperçu part chez
  le prescripteur. À doute égal, on signale.

La comparaison doit franchir la barrière dictée/écrit : une orthophoniste dicte
« moins deux écarts-types » et le modèle écrit « -2 ET ». Les nombres énoncés
en mots sont donc convertis avant comparaison, sans quoi tout chiffre
légitimement dicté serait signalé à tort.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# --- Nombres écrits en mots (français parlé) --------------------------------

_UNITES: dict[str, int] = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
    "seize": 16,
}
_DIZAINES: dict[str, int] = {
    "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
    "cent": 100, "cents": 100,
}
_MOTS_NOMBRE = set(_UNITES) | set(_DIZAINES) | {"vingt", "vingts", "demi", "demie"}

# Mots qui *modifient* le nombre suivant sans en faire partie.
_NEGATIFS = {"moins", "-"}


def _sans_accents(s: str) -> str:
    d = unicodedata.normalize("NFD", s)
    return "".join(c for c in d if unicodedata.category(c) != "Mn")


def _canonique(v: float) -> str:
    """Forme comparable d'une valeur : « -2.5 », « 28 » (pas « -2.50 »)."""
    if v == int(v):
        return str(int(v))
    return f"{v:g}"


def _valeur_mots(mots: list[str]) -> float:
    """Additionne une suite de mots-nombres français consécutifs.

    Couvre les formes cliniques usuelles de 0 à 999 : « vingt-huit »,
    « dix-huit », « soixante-dix », « quatre-vingt-douze », « deux ans et
    demi ». Les formes exotiques restent hors champ : les rater ne fait que
    signaler un chiffre de plus (faute bénigne, cf. en-tête du module)."""
    total = 0.0
    precedent: int | None = None
    for m in mots:
        if m in ("demi", "demie"):
            total += 0.5
            continue
        if m in ("vingt", "vingts"):
            # « quatre-vingts » est multiplicatif, « soixante-vingt » n'existe pas.
            if precedent == 4 and total == 4:
                total = 80.0
            else:
                total += 20
            precedent = 20
            continue
        u = _UNITES.get(m)
        if u is not None:
            total += u
            precedent = u
            continue
        d = _DIZAINES.get(m)
        if d is not None:
            total += d
            precedent = d
    return total


def _nombres_en_mots(texte: str) -> set[str]:
    """Valeurs énoncées en mots, y compris « moins deux virgule cinq »."""
    jetons = re.split(r"[^a-z0-9]+", _sans_accents(texte.lower()))
    valeurs: set[str] = set()
    i = 0
    while i < len(jetons):
        if jetons[i] not in _MOTS_NOMBRE:
            i += 1
            continue
        # Groupe de mots-nombres, en sautant les liants « et » / « - ».
        groupe: list[str] = []
        j = i
        while j < len(jetons):
            if jetons[j] in _MOTS_NOMBRE:
                groupe.append(jetons[j])
                j += 1
            elif jetons[j] == "et" and j + 1 < len(jetons) and jetons[j + 1] in _MOTS_NOMBRE:
                j += 1
            else:
                break
        entier = _valeur_mots(groupe)
        # Partie décimale : « … virgule cinq ».
        if j < len(jetons) and jetons[j] == "virgule":
            k = j + 1
            decimales: list[str] = []
            while k < len(jetons) and jetons[k] in _MOTS_NOMBRE:
                decimales.append(jetons[k])
                k += 1
            if decimales:
                frac = _valeur_mots(decimales)
                entier += frac / (10 ** len(str(int(frac))))
                j = k
        negatif = i > 0 and jetons[i - 1] in _NEGATIFS
        valeurs.add(_canonique(-entier if negatif else entier))
        valeurs.add(_canonique(entier))  # tolérance de signe côté source
        i = j if j > i else i + 1
    return valeurs


_NOMBRE_CHIFFRES = re.compile(r"(-|moins\s+)?(\d+(?:[.,]\d+)?)")


def _nombres_en_chiffres(texte: str) -> set[str]:
    valeurs: set[str] = set()
    bas = _sans_accents(texte.lower())
    for m in _NOMBRE_CHIFFRES.finditer(bas):
        brut = float(m.group(2).replace(",", "."))
        valeurs.add(_canonique(brut))
        if m.group(1):
            valeurs.add(_canonique(-brut))
    return valeurs


def valeurs_numeriques(texte: str) -> set[str]:
    """Toutes les valeurs numériques d'un texte, chiffres ET mots confondus."""
    return _nombres_en_chiffres(texte) | _nombres_en_mots(texte)


# --- Vérifications ----------------------------------------------------------

def chiffres_non_sources(propose: str, sources: Iterable[str]) -> list[str]:
    """Nombres du texte proposé introuvables dans le matériau source.

    Seuls les nombres écrits **en chiffres** sont contrôlés : c'est sous cette
    forme que le modèle restitue les étalonnages, et un mot-nombre isolé
    (« deux séances ») relève de la prose, pas de la mesure."""
    connues: set[str] = set()
    for s in sources:
        connues |= valeurs_numeriques(s or "")
    suspects: list[str] = []
    for m in _NOMBRE_CHIFFRES.finditer(_sans_accents(propose.lower())):
        brut = float(m.group(2).replace(",", "."))
        # Contrôle au signe près : un « -3 » proposé alors que la dictée ne
        # contenait qu'un « trois » (dans « trois minutes ») est précisément le
        # genre de transposition qu'on cherche à voir. Les sources, elles,
        # enregistrent les deux signes — c'est leur formulation qui varie.
        signe = -brut if m.group(1) else brut
        if _canonique(signe) in connues:
            continue
        libelle = _canonique(signe)
        if libelle not in suspects:
            suspects.append(libelle)
    return suspects


_NB = r"(-\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
# Motifs ciblés plutôt qu'une fenêtre de caractères : « écart-type (-2,5) et
# percentile (-3) » ne doit signaler que le percentile, pas l'écart-type voisin.
_PERCENTILE_VALEUR = [
    re.compile(rf"percentile\s*(?:de\s+|:\s*|=\s*)?\(?\s*{_NB}", re.I),
    re.compile(rf"{_NB}\s*(?:e|è?me|ᵉ)?\s*percentile", re.I),
]


def percentiles_hors_bornes(texte: str) -> list[str]:
    """Valeurs présentées comme des percentiles hors de l'intervalle 0-100.

    Un « percentile -3 » n'existe pas : c'est la signature d'un modèle qui a
    transposé un écart-type en percentile. Erreur détectable sans connaître la
    dictée, donc vérifiée séparément."""
    hors: list[str] = []
    for motif in _PERCENTILE_VALEUR:
        for v in motif.finditer(texte):
            try:
                val = float(v.group(1).replace(" ", "").replace(",", "."))
            except ValueError:
                continue
            if (val < 0 or val > 100) and _canonique(val) not in hors:
                hors.append(_canonique(val))
    return hors


def signalements(propose: str, sources: Iterable[str]) -> list[str]:
    """Messages courts prêts à afficher pour une rubrique proposée."""
    msgs: list[str] = []
    inconnus = chiffres_non_sources(propose, sources)
    if inconnus:
        msgs.append(
            "chiffre(s) absent(s) de la dictée : " + ", ".join(inconnus)
        )
    faux_pct = percentiles_hors_bornes(propose)
    if faux_pct:
        msgs.append(
            "percentile(s) impossible(s) : " + ", ".join(faux_pct)
        )
    return msgs
