"""Texte riche des rubriques : Markdown restreint, lu et écrit ici seulement.

Une rubrique de compte-rendu porte du gras (nom d'un test, résultat saillant),
de l'italique, du souligné (intertitre à l'intérieur d'une rubrique) et des
listes (axes de rééducation, aménagements). Le contenu reste une chaîne de
texte dans la base : un contenu existant, en texte brut, est déjà valide.

Éléments admis, et rien d'autre (pas de titres, de tableaux, de liens) :

- ``**gras**``, ``*italique*``, ``<u>souligné</u>`` (Markdown n'a pas de
  souligné), combinables ;
- listes à puces (``- item``) et numérotées (``1. item``), un élément par
  ligne, continuation d'un élément par une ligne indentée de deux espaces ;
- paragraphes séparés par une ligne vide ; un retour à la ligne simple reste
  un retour à la ligne dans le paragraphe.

Un marqueur non fermé ou mal placé est du texte, jamais une erreur : le
texte d'un compte-rendu ne doit pas pouvoir « casser ».
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Segment:
    texte: str
    gras: bool = False
    italique: bool = False
    souligne: bool = False

    @property
    def simple(self) -> bool:
        return not (self.gras or self.italique or self.souligne)


@dataclass
class Paragraphe:
    segments: list[Segment] = field(default_factory=list)


@dataclass
class Liste:
    ordonnee: bool
    items: list[list[Segment]] = field(default_factory=list)


Bloc = Paragraphe | Liste

# --- Marqueurs en ligne -------------------------------------------------------
# Un marqueur ouvre s'il est suivi d'un caractère visible et ferme s'il en est
# précédé : « 5 * 3 » ou « (*) » restent du texte. Les motifs acceptent un
# retour à la ligne à l'intérieur (un passage en gras peut couvrir deux lignes
# d'un même paragraphe).
_GRAS_ITAL = re.compile(r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*", re.S)
_GRAS = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
_ITAL = re.compile(r"(?<!\*)\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?!\*)", re.S)
_SOUL = re.compile(r"<u>(.+?)</u>", re.S)
# Ordre de préférence à position égale : le marqueur le plus long d'abord.
_MARQUEURS = (
    (_GRAS_ITAL, {"gras": True, "italique": True}),
    (_GRAS, {"gras": True}),
    (_ITAL, {"italique": True}),
    (_SOUL, {"souligne": True}),
)

# --- Lignes de bloc -----------------------------------------------------------
_PUCE = re.compile(r"^[-*•]\s+(.*)$")
_NUMERO = re.compile(r"^\d{1,3}[.)]\s+(.*)$")
_CONTINUATION = re.compile(r"^\s{2,}(\S.*)$")


def _item_apparent(ligne: str) -> bool:
    """La ligne serait lue comme un élément de liste (« - 2 ET », « 1. … »)."""
    return bool(_PUCE.match(ligne) or _NUMERO.match(ligne))


def _fusionner(segments: list[Segment]) -> list[Segment]:
    """Fusionne les segments voisins de même mise en forme, retire les vides."""
    out: list[Segment] = []
    for s in segments:
        if not s.texte:
            continue
        if out and (out[-1].gras, out[-1].italique, out[-1].souligne) == (
            s.gras, s.italique, s.souligne
        ):
            out[-1].texte += s.texte
        else:
            out.append(Segment(s.texte, s.gras, s.italique, s.souligne))
    return out


def _inline(texte: str, **etat: bool) -> list[Segment]:
    """Découpe un texte en segments selon les marqueurs en ligne (récursif)."""
    out: list[Segment] = []
    pos = 0
    while pos < len(texte):
        meilleur = None
        for rx, drapeaux in _MARQUEURS:
            m = rx.search(texte, pos)
            if m and (meilleur is None or m.start() < meilleur[0].start()):
                meilleur = (m, drapeaux)
        if meilleur is None:
            out.append(Segment(texte[pos:], **etat))
            break
        m, drapeaux = meilleur
        if m.start() > pos:
            out.append(Segment(texte[pos:m.start()], **etat))
        out.extend(_inline(m.group(1), **{**etat, **drapeaux}))
        pos = m.end()
    return _fusionner(out)


def analyser(texte: str | None) -> list[Bloc]:
    """Texte d'une rubrique -> blocs (paragraphes et listes) de segments."""
    blocs: list[Bloc] = []
    para: list[str] = []
    liste: tuple[bool, list[str]] | None = None  # (ordonnée, items bruts)

    def clore_para() -> None:
        if para:
            blocs.append(Paragraphe(_inline("\n".join(para))))
            para.clear()

    def clore_liste() -> None:
        nonlocal liste
        if liste is not None:
            ordonnee, items = liste
            blocs.append(Liste(ordonnee, [_inline(i) for i in items]))
            liste = None

    lignes = (texte or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for ligne in lignes:
        if not ligne.strip():
            clore_para()
            clore_liste()
            continue
        if liste is not None:
            suite = _CONTINUATION.match(ligne)
            if suite:
                liste[1][-1] += "\n" + suite.group(1).rstrip()
                continue
        propre = ligne.strip()
        if propre.startswith("\\") and _item_apparent(propre[1:]):
            # Ligne de paragraphe protégée par serialiser() : « \- 2 ET ».
            clore_liste()
            para.append(propre[1:])
            continue
        item = _PUCE.match(propre)
        ordonnee = False
        if not item:
            item = _NUMERO.match(propre)
            ordonnee = bool(item)
        if item:
            clore_para()
            if liste is None or liste[0] != ordonnee:
                clore_liste()
                liste = (ordonnee, [])
            liste[1].append(item.group(1).strip())
        else:
            clore_liste()
            para.append(propre)
    clore_para()
    clore_liste()
    return blocs


def _segment_md(s: Segment) -> str:
    if s.simple:
        return s.texte
    # Les espaces de bord sortent des marqueurs : « ** gras** » n'ouvre pas.
    m = re.match(r"^(\s*)(.*?)(\s*)$", s.texte, re.S)
    avant, coeur, apres = m.groups()
    if not coeur:
        return s.texte
    if s.souligne:
        coeur = f"<u>{coeur}</u>"
    if s.gras and s.italique:
        coeur = f"***{coeur}***"
    elif s.gras:
        coeur = f"**{coeur}**"
    elif s.italique:
        coeur = f"*{coeur}*"
    return avant + coeur + apres


def serialiser_segments(segments: list[Segment]) -> str:
    """Segments -> Markdown restreint (une ligne logique, retours conservés)."""
    return "".join(_segment_md(s) for s in _fusionner(segments))


def serialiser(blocs: list[Bloc]) -> str:
    """Blocs -> Markdown restreint canonique (« - » pour les puces, ligne vide
    entre les blocs, continuation d'un élément indentée de deux espaces)."""
    out: list[str] = []
    for b in blocs:
        if isinstance(b, Paragraphe):
            # Une ligne de paragraphe qui ressemble à un élément de liste
            # (« - 2 ET ») est protégée par une barre oblique inverse, que
            # analyser() retire : le signe moins d'un écart-type n'est pas une puce.
            out.append("\n".join(
                ("\\" + ligne) if _item_apparent(ligne) else ligne
                for ligne in (x.strip() for x in serialiser_segments(b.segments).split("\n"))
            ))
        else:
            lignes = []
            for i, item in enumerate(b.items, 1):
                prefixe = f"{i}. " if b.ordonnee else "- "
                corps = [x.strip() for x in serialiser_segments(item).split("\n") if x.strip()]
                lignes.append(prefixe + "\n  ".join(corps))
            out.append("\n".join(lignes))
    return "\n\n".join(x for x in out if x.strip())


def canonique(texte: str | None) -> str:
    """Réécrit un contenu dans sa forme canonique (analyse puis sérialisation)."""
    return serialiser(analyser(texte))


def en_clair(texte: str | None, numeroter: bool = True) -> str:
    """Texte sans aucun marqueur, listes rendues par « - » ou « 1. ».

    ``numeroter=False`` rend aussi les listes numérotées par des tirets : les
    vérificateurs de chiffres ne doivent pas prendre un numéro d'élément pour
    une valeur clinique proposée par le modèle."""
    out: list[str] = []
    for b in analyser(texte):
        if isinstance(b, Paragraphe):
            out.append("".join(s.texte for s in b.segments))
        else:
            lignes = []
            for i, item in enumerate(b.items, 1):
                prefixe = f"{i}. " if (b.ordonnee and numeroter) else "- "
                lignes.append(prefixe + "".join(s.texte for s in item).replace("\n", "\n  "))
            out.append("\n".join(lignes))
    return "\n\n".join(x for x in out if x.strip())


def contient_mise_en_forme(texte: str | None) -> bool:
    """True si le texte porte au moins un marqueur reconnu (gras, liste…)."""
    for b in analyser(texte):
        if isinstance(b, Liste):
            return True
        if any(not s.simple for s in b.segments):
            return True
    return False
