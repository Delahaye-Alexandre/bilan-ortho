"""Vérification des mises à jour de l'application.

Seul appel réseau externe du produit : un GET vers l'API GitHub Releases,
déclenché par l'utilisateur (bouton des Paramètres) ou par l'option opt-in
« vérification au démarrage » (désactivée par défaut). Aucune donnée n'est
transmise — pas de télémétrie — et rien ici ne touche au coffre : le flux de
données patient reste 100 % local (voir docs/RGPD-registre-traitements.md).

L'installation d'une mise à jour reste un geste manuel : télécharger
l'installeur depuis la page GitHub et l'exécuter (il gère la mise à niveau
par-dessus l'existant en préservant les données).
"""
from __future__ import annotations

import httpx

from . import __version__

DEPOT_GITHUB = "Delahaye-Alexandre/bilan-ortho"
URL_API_RELEASE = f"https://api.github.com/repos/{DEPOT_GITHUB}/releases/latest"
# Page de téléchargement ouverte côté client : construite ICI et jamais reprise
# de la réponse réseau — le navigateur n'ouvrira jamais une URL venue d'ailleurs.
URL_TELECHARGEMENT = f"https://github.com/{DEPOT_GITHUB}/releases/latest"
TIMEOUT_S = 5


class MajIndisponible(Exception):
    """La vérification n'a pas abouti (hors ligne, GitHub injoignable…)."""


def _version_tuple(version: str) -> tuple[int, ...] | None:
    """« v1.6.0 » ou « 1.6.0 » -> (1, 6, 0) ; None si le format est inattendu."""
    try:
        return tuple(int(p) for p in version.strip().lstrip("vV").split("."))
    except ValueError:
        return None


def est_plus_recente(disponible: str, actuelle: str) -> bool:
    """True si `disponible` est strictement plus récente que `actuelle`.

    Comparaison numérique champ à champ (1.10 > 1.9). Format inattendu
    (pré-release, tag exotique) -> False : ne jamais proposer une version
    dont on ne sait pas la situer par rapport à celle installée."""
    d, a = _version_tuple(disponible), _version_tuple(actuelle)
    if d is None or a is None:
        return False
    return d > a


async def derniere_version() -> str:
    """Tag de la dernière release *publiée* (ex. « v1.7.0 »).

    Les brouillons et pré-releases GitHub sont exclus par l'API elle-même
    (`releases/latest`)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                URL_API_RELEASE, headers={"Accept": "application/vnd.github+json"}
            )
            r.raise_for_status()
            return str(r.json().get("tag_name") or "")
    except (httpx.HTTPError, ValueError) as e:
        raise MajIndisponible(
            "Vérification impossible : hors ligne, ou GitHub injoignable."
        ) from e


async def verifier() -> dict:
    """Compare la dernière release publiée à la version en cours d'exécution."""
    tag = await derniere_version()
    return {
        "version_actuelle": __version__,
        "version_disponible": tag.lstrip("vV"),
        "maj_disponible": est_plus_recente(tag, __version__),
        "url": URL_TELECHARGEMENT,
    }
