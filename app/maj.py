"""Mises à jour de l'application : vérification, téléchargement vérifié,
installation.

Seuls appels réseau externes du produit, et toujours vers GitHub :

- la **vérification** (GET de l'API GitHub Releases), déclenchée par le bouton
  des Paramètres ou, au plus une fois par jour, au démarrage (réglage
  ``maj.verification_auto``, activé par défaut, désactivable) ;
- le **téléchargement** de l'installeur et de ses empreintes, uniquement quand
  le praticien clique « Installer maintenant ».

Aucune donnée n'est transmise (pas de télémétrie) ; rien ici ne touche au
coffre, sinon pour en faire une sauvegarde avant d'installer. Le flux de
données patient reste 100 % local (voir docs/RGPD-registre-traitements.md).

Chaîne de confiance de l'installation en un clic : la CI publie, à côté de
l'installeur, un fichier ``SHA256SUMS`` et sa signature Ed25519
``SHA256SUMS.sig``. L'app vérifie la signature avec la clé publique embarquée
ci-dessous, puis l'empreinte de l'installeur téléchargé, et ne lance jamais un
fichier qui n'a pas passé ces deux contrôles. Les URL sont construites ICI à
partir du numéro de version, jamais reprises d'une réponse réseau.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import __version__, config

DEPOT_GITHUB = "Delahaye-Alexandre/bilan-ortho"
URL_API_RELEASE = f"https://api.github.com/repos/{DEPOT_GITHUB}/releases/latest"
# Page de téléchargement ouverte côté client : construite ICI et jamais reprise
# de la réponse réseau — le navigateur n'ouvrira jamais une URL venue d'ailleurs.
URL_TELECHARGEMENT = f"https://github.com/{DEPOT_GITHUB}/releases/latest"
URL_ASSETS = f"https://github.com/{DEPOT_GITHUB}/releases/download"
NOM_INSTALLEUR = "BilanOrtho-Setup-{version}.exe"
NOM_SOMMES = "SHA256SUMS"
NOM_SIGNATURE = "SHA256SUMS.sig"

# Clé publique Ed25519 (base64, 32 octets) qui authentifie les releases. La
# clé privée correspondante n'existe que dans le secret GitHub
# BILAN_ORTHO_CLE_PRIVEE (et dans la copie de secours du mainteneur, hors
# dépôt). Changer de clé = publier d'abord une version qui embarque la
# nouvelle clé publique, signée avec l'ancienne. Vide : aucune installation
# automatique possible (fork sans clé), le lien de téléchargement reste.
CLE_PUBLIQUE_RELEASES = "bwATEoKGvxvlwULpkb2lo/CbMUOEipPZeGIP8PW2jPc="

TAILLE_MAX_INSTALLEUR = 400 * 1024 * 1024
TAILLE_MAX_PETIT = 64 * 1024
INTERVALLE_AUTO = timedelta(hours=24)
TIMEOUT_S = 5
TIMEOUT_TELECHARGEMENT_S = 120  # par lecture, pas pour tout le fichier
_VERSION_RE = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")
CLE_ETAT = "maj_etat"  # clé de la table config qui porte l'état local

# Deux causes d'échec bien distinctes — ne jamais affirmer au praticien qu'il
# est hors ligne alors que sa connexion fonctionne.
MSG_INJOIGNABLE = "Vérification impossible : hors ligne, ou GitHub injoignable."
MSG_AUCUNE_RELEASE = (
    "Aucune version publiée n'est accessible pour le moment. "
    "Votre installation reste fonctionnelle ; réessayez plus tard."
)
MSG_INSTALLATION_IMPOSSIBLE = (
    "L'installation en un clic n'est disponible que dans l'application Windows "
    "installée. Depuis un dépôt cloné : git pull, puis "
    "pip install -r requirements-lock.txt, puis relancez le serveur."
)


class MajIndisponible(Exception):
    """La vérification n'a pas abouti (hors ligne, GitHub injoignable…)."""


class MajRefusee(Exception):
    """Téléchargement ou installation refusé : intégrité, plateforme, état."""


# --- Versions ------------------------------------------------------------------

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


def installation_possible() -> bool:
    """L'installation en un clic suppose l'application compilée sous Windows :
    c'est l'installeur Inno Setup qui remplace les fichiers et relance l'app."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


# --- Notes de release --------------------------------------------------------

_TITRE_NOUVEAUTES = re.compile(r"^##\s*(?:\S+\s+)?Nouveaut", re.I | re.M)
_LIEN_MD = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def extraire_nouveautes(corps: str | None, max_car: int = 1500) -> str:
    """Section « Nouveautés » des notes de release, en texte simple.

    Les notes publiées par la CI commencent par la marche à suivre pour
    installer, puis reprennent la section du CHANGELOG : c'est cette seconde
    partie qui répond à « qu'est-ce qui change pour moi ? ». Balisage Markdown
    retiré : le texte est affiché tel quel, jamais interprété."""
    texte = (corps or "").replace("\r\n", "\n")
    m = _TITRE_NOUVEAUTES.search(texte)
    if m:
        texte = texte[m.end():]
        texte = texte.split("\n## ", 1)[0]
        texte = texte.split("\n", 1)[1] if "\n" in texte else ""
    lignes = []
    for ligne in texte.splitlines():
        ligne = _LIEN_MD.sub(r"\1", ligne)
        ligne = ligne.replace("**", "").replace("`", "")
        ligne = re.sub(r"^\s*[-*]\s+", "• ", ligne)
        if ligne.strip():
            lignes.append(ligne.rstrip())
    out = "\n".join(lignes).strip()
    if len(out) > max_car:
        out = out[:max_car].rsplit(" ", 1)[0] + "…"
    return out


# --- Vérification ---------------------------------------------------------------

async def derniere_release() -> dict:
    """Dernière release *publiée* : ``{"tag", "notes", "publiee_le"}``.

    Les brouillons et pré-releases GitHub sont exclus par l'API elle-même
    (`releases/latest`)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(
                URL_API_RELEASE, headers={"Accept": "application/vnd.github+json"}
            )
            r.raise_for_status()
            corps = r.json()
    except httpx.HTTPStatusError as e:
        # 404 : le dépôt n'a aucune release publiée, ou n'est pas accessible
        # sans authentification. La connexion, elle, fonctionne — le dire.
        # (Sous-classe de HTTPError : ce cas doit rester avant le suivant.)
        if e.response.status_code == 404:
            raise MajIndisponible(MSG_AUCUNE_RELEASE) from e
        raise MajIndisponible(MSG_INJOIGNABLE) from e
    except (httpx.HTTPError, ValueError) as e:
        raise MajIndisponible(MSG_INJOIGNABLE) from e
    if not isinstance(corps, dict):
        raise MajIndisponible(MSG_INJOIGNABLE)
    return {
        "tag": str(corps.get("tag_name") or ""),
        "notes": extraire_nouveautes(str(corps.get("body") or "")),
        "publiee_le": str(corps.get("published_at") or "")[:10],
    }


async def derniere_version() -> str:
    """Tag de la dernière release publiée (ex. « v1.7.0 »)."""
    return (await derniere_release())["tag"]


async def verifier() -> dict:
    """Compare la dernière release publiée à la version en cours d'exécution."""
    rel = await derniere_release()
    return {
        "version_actuelle": __version__,
        "version_disponible": rel["tag"].lstrip("vV"),
        "maj_disponible": est_plus_recente(rel["tag"], __version__),
        "url": URL_TELECHARGEMENT,
        "notes": rel["notes"],
        "publiee_le": rel["publiee_le"],
        "installation_possible": installation_possible(),
        "verifiee_le": datetime.now(UTC).isoformat(timespec="seconds"),
    }


# --- État local (table config, clé « maj_etat ») ---------------------------------
# Séparé des surcharges de config : ce n'est pas un réglage du praticien mais
# une mémoire de l'app (dernière vérification, version ignorée, information
# affichée), qui ne doit pas apparaître comme « personnalisé » dans Paramètres.

def etat_lire(con) -> dict:
    row = con.execute("SELECT value FROM config WHERE key = ?", (CLE_ETAT,)).fetchone()
    if not row:
        return {}
    try:
        etat = json.loads(row[0])
    except ValueError:
        return {}
    return etat if isinstance(etat, dict) else {}


def etat_ecrire(con, **champs) -> dict:
    """Fusionne les champs donnés dans l'état (None = supprimer). Retourne l'état."""
    etat = etat_lire(con)
    for k, v in champs.items():
        if v is None:
            etat.pop(k, None)
        else:
            etat[k] = v
    con.execute(
        "INSERT INTO config(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (CLE_ETAT, json.dumps(etat, ensure_ascii=False)),
    )
    return etat


def doit_verifier(etat: dict, maintenant: datetime | None = None) -> bool:
    """Vérification automatique due ? Au plus une par INTERVALLE_AUTO."""
    derniere = etat.get("derniere")
    if not derniere:
        return True
    try:
        d = datetime.fromisoformat(str(derniere))
    except ValueError:
        return True
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    maintenant = maintenant or datetime.now(UTC)
    return maintenant - d >= INTERVALLE_AUTO


def appliquer_etat(resultat: dict, etat: dict) -> dict:
    """Marque la version ignorée par le praticien : la vérification
    automatique n'en fait plus un bandeau, la vérification manuelle la montre
    quand même, en le disant."""
    out = dict(resultat)
    out["ignoree"] = bool(
        out.get("version_disponible") and out.get("version_disponible") == etat.get("ignoree")
    )
    return out


# --- Téléchargement vérifié -------------------------------------------------------

def dossier_maj() -> Path:
    d = config.data_dir() / "maj"
    d.mkdir(parents=True, exist_ok=True)
    return d


def url_asset(version: str, nom: str) -> str:
    """URL d'un fichier de release, construite localement (jamais reprise d'une
    réponse réseau) ; le numéro de version est contraint au format x.y.z."""
    if not _VERSION_RE.match(version or ""):
        raise MajRefusee("Numéro de version invalide.")
    return f"{URL_ASSETS}/v{version}/{nom}"


def verifier_signature(
    donnees: bytes, signature_b64: str, cle_publique_b64: str | None = None
) -> None:
    """Lève MajRefusee si `donnees` n'est pas signé par la clé de publication."""
    if cle_publique_b64 is None:
        cle_publique_b64 = CLE_PUBLIQUE_RELEASES  # lu à l'appel (tests, rotation)
    if not cle_publique_b64:
        raise MajRefusee(
            "Aucune clé de publication n'est embarquée dans cette version : "
            "installation automatique impossible. Téléchargez l'installeur depuis GitHub."
        )
    try:
        cle = Ed25519PublicKey.from_public_bytes(base64.b64decode(cle_publique_b64))
        signature = base64.b64decode((signature_b64 or "").strip())
        cle.verify(signature, donnees)
    except (InvalidSignature, ValueError) as e:
        raise MajRefusee(
            "La signature des empreintes ne correspond pas à la clé de publication "
            "de Bilan Ortho : installation refusée."
        ) from e


def somme_attendue(sommes: str, nom: str) -> str:
    """Empreinte SHA-256 annoncée pour `nom` dans un fichier SHA256SUMS."""
    for ligne in (sommes or "").splitlines():
        parts = ligne.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == nom and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    raise MajRefusee(f"Aucune empreinte publiée pour {nom} : installation refusée.")


# Fichiers téléchargés ET vérifiés dans cette session : version -> (chemin, sha256).
_VERIFIES: dict[str, tuple[Path, str]] = {}


async def _petit_fichier(client: httpx.AsyncClient, url: str) -> bytes:
    r = await client.get(url, follow_redirects=True)
    r.raise_for_status()
    if len(r.content) > TAILLE_MAX_PETIT:
        raise MajRefusee("Fichier d'empreintes anormalement volumineux : refusé.")
    return r.content


async def telecharger(version: str, dossier: Path | None = None) -> AsyncIterator[dict]:
    """Télécharge et vérifie l'installeur d'une version. Générateur d'événements
    (NDJSON côté route) : ``{"etape": …}``, ``{"etape": "telechargement",
    "recu", "total"}``, puis ``{"fini": true, "fichier", "octets"}`` ou
    ``{"erreur": …}``. Un fichier qui échoue à la vérification est effacé."""
    dossier = dossier or dossier_maj()
    nom = NOM_INSTALLEUR.format(version=version)
    cible = dossier / nom
    partiel = dossier / (nom + ".part")
    try:
        url_exe = url_asset(version, nom)
        # Les anciens installeurs ne servent plus à rien : un seul à la fois.
        for ancien in dossier.glob("BilanOrtho-Setup-*.exe*"):
            if ancien != cible:
                ancien.unlink(missing_ok=True)
        yield {"etape": "sommes"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_TELECHARGEMENT_S, connect=TIMEOUT_S)) as client:
            sommes = await _petit_fichier(client, url_asset(version, NOM_SOMMES))
            signature = await _petit_fichier(client, url_asset(version, NOM_SIGNATURE))
            verifier_signature(sommes, signature.decode("ascii", errors="ignore"))
            attendu = somme_attendue(sommes.decode("utf-8", errors="ignore"), nom)
            h = hashlib.sha256()
            recu = 0
            async with client.stream("GET", url_exe, follow_redirects=True) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                if total > TAILLE_MAX_INSTALLEUR:
                    raise MajRefusee("Installeur anormalement volumineux : refusé.")
                yield {"etape": "telechargement", "recu": 0, "total": total}
                with open(partiel, "wb") as f:
                    dernier_signal = 0
                    async for morceau in r.aiter_bytes(256 * 1024):
                        f.write(morceau)
                        h.update(morceau)
                        recu += len(morceau)
                        if recu > TAILLE_MAX_INSTALLEUR:
                            raise MajRefusee("Installeur anormalement volumineux : refusé.")
                        if recu - dernier_signal >= 1024 * 1024:
                            dernier_signal = recu
                            yield {"etape": "telechargement", "recu": recu, "total": total}
        yield {"etape": "verification"}
        if h.hexdigest() != attendu:
            raise MajRefusee(
                "L'empreinte de l'installeur téléchargé ne correspond pas à celle "
                "publiée : fichier corrompu ou altéré, installation refusée."
            )
        partiel.replace(cible)
        _VERIFIES[version] = (cible, attendu)
        yield {"fini": True, "fichier": nom, "octets": recu}
    except MajRefusee as e:
        partiel.unlink(missing_ok=True)
        yield {"erreur": str(e)}
    except httpx.HTTPStatusError as e:
        partiel.unlink(missing_ok=True)
        if e.response.status_code == 404:
            yield {"erreur": "Cette version n'a pas de fichiers d'installation publiés (ou pas encore)."}
        else:
            yield {"erreur": MSG_INJOIGNABLE}
    except (httpx.HTTPError, OSError):
        partiel.unlink(missing_ok=True)
        yield {"erreur": "Téléchargement interrompu : hors ligne, ou GitHub injoignable."}


def fichier_verifie(version: str) -> Path:
    """Chemin de l'installeur téléchargé ET vérifié dans cette session, dont
    l'empreinte est recalculée à l'instant (rien n'a bougé sur le disque)."""
    entree = _VERIFIES.get(version)
    if not entree or not entree[0].exists():
        raise MajRefusee("Téléchargez d'abord la mise à jour : aucun installeur vérifié.")
    chemin, attendu = entree
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloc)
    if h.hexdigest() != attendu:
        chemin.unlink(missing_ok=True)
        _VERIFIES.pop(version, None)
        raise MajRefusee("L'installeur a changé sur le disque depuis sa vérification : refusé.")
    return chemin


def lancer_installeur(chemin: Path, port: int) -> None:
    """Lance l'installeur Inno Setup, détaché de ce processus, en silencieux.

    Il ferme l'application (CloseApplications=force et taskkill dans
    PrepareToInstall), remplace les fichiers, puis relance BilanOrtho.exe sur
    le même port (paramètre /RELANCER, voir installeur.iss et lanceur.py) :
    la page ouverte se reconnecte seule. Journal dans <données>/maj."""
    args = [
        str(chemin), "/SILENT", "/NORESTART", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS",
        f"/RELANCER={int(port)}", f"/LOG={dossier_maj() / 'installeur.log'}",
    ]
    drapeaux = 0
    if sys.platform == "win32":
        drapeaux = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        args, creationflags=drapeaux, close_fds=True, cwd=str(chemin.parent),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
