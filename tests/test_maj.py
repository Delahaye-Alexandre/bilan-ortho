"""Vérification des mises à jour : comparaison de versions et route /api/maj.

Comme le reste de la suite, tout tourne hors ligne : l'appel à l'API GitHub
(seul appel réseau externe de l'application) est systématiquement mocké.
"""
from __future__ import annotations

import asyncio
from datetime import UTC

import httpx
import pytest

from app import __version__, maj

# --- Comparaison de versions --------------------------------------------------

@pytest.mark.parametrize(
    ("disponible", "actuelle", "attendu"),
    [
        ("v1.7.0", "1.6.0", True),
        ("1.7.0", "1.6.0", True),          # tag sans préfixe « v »
        ("v1.6.0", "1.6.0", False),        # à jour
        ("v1.5.9", "1.6.0", False),        # release plus ancienne (rétrogradage refusé)
        ("v2.0.0", "1.9.9", True),
        ("v1.10.0", "1.9.0", True),        # comparaison numérique, pas lexicale
        ("v1.7", "1.6.0", True),           # tag court
        ("", "1.6.0", False),              # release sans tag
        ("v1.7.0-beta", "1.6.0", False),   # format inattendu -> prudence
        ("abc", "1.6.0", False),
    ],
)
def test_est_plus_recente(disponible, actuelle, attendu):
    assert maj.est_plus_recente(disponible, actuelle) is attendu


# --- derniere_version : client HTTP réel, transport mocké ----------------------

def _client_mocke(monkeypatch, reponse):
    """Remplace httpx.AsyncClient (vu de maj.py) par un client sans réseau."""
    client_reel = httpx.AsyncClient

    def repond(requete):
        assert str(requete.url) == maj.URL_API_RELEASE
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    def fabrique(**kwargs):
        return client_reel(transport=httpx.MockTransport(repond))

    monkeypatch.setattr(maj.httpx, "AsyncClient", fabrique)


def test_derniere_version_nominale(monkeypatch):
    _client_mocke(monkeypatch, httpx.Response(200, json={"tag_name": "v9.9.9"}))
    assert asyncio.run(maj.derniere_version()) == "v9.9.9"


@pytest.mark.parametrize(
    "reponse",
    [
        httpx.ConnectError("réseau coupé"),
        httpx.Response(500, json={"message": "Server Error"}),  # panne côté GitHub
        httpx.Response(200, content=b"pas du JSON"),
    ],
)
def test_derniere_version_indisponible(monkeypatch, reponse):
    _client_mocke(monkeypatch, reponse)
    with pytest.raises(maj.MajIndisponible, match="hors ligne"):
        asyncio.run(maj.derniere_version())


def test_derniere_version_404_ne_dit_pas_hors_ligne(monkeypatch):
    """404 = aucune release publiée, ou dépôt non accessible sans compte.

    La connexion fonctionne : l'application ne doit pas affirmer le contraire
    à la personne qui l'utilise (cas vécu tant que le dépôt était privé)."""
    _client_mocke(monkeypatch, httpx.Response(404, json={"message": "Not Found"}))
    with pytest.raises(maj.MajIndisponible) as e:
        asyncio.run(maj.derniere_version())
    assert str(e.value) == maj.MSG_AUCUNE_RELEASE
    assert "hors ligne" not in str(e.value)


# --- Route /api/maj -------------------------------------------------------------

@pytest.fixture()
def client_verrouille(data_dir):
    """Client SANS déverrouillage : la vérification ne touche pas au coffre et
    doit répondre même verrouillée (comme /api/status)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def test_maj_disponible(client_verrouille, monkeypatch):
    async def fausse_release():
        return {"tag": "v99.0.0", "notes": "• Une nouveauté.", "publiee_le": "2026-09-03"}

    monkeypatch.setattr(maj, "derniere_release", fausse_release)
    r = client_verrouille.get("/api/maj")
    assert r.status_code == 200
    corps = r.json()
    assert corps["maj_disponible"] is True
    assert corps["version_disponible"] == "99.0.0"
    assert corps["version_actuelle"] == __version__
    # L'URL ouverte par le client est construite côté serveur, jamais reprise
    # de la réponse GitHub.
    assert corps["url"] == maj.URL_TELECHARGEMENT
    assert corps["notes"] == "• Une nouveauté." and corps["publiee_le"] == "2026-09-03"
    assert corps["installation_possible"] is False  # tests : ni Windows ni gelé


def test_maj_a_jour(client_verrouille, monkeypatch):
    async def fausse_release():
        return {"tag": f"v{__version__}", "notes": "", "publiee_le": ""}

    monkeypatch.setattr(maj, "derniere_release", fausse_release)
    corps = client_verrouille.get("/api/maj").json()
    assert corps["maj_disponible"] is False
    assert corps["version_disponible"] == __version__


def test_maj_hors_ligne(client_verrouille, monkeypatch):
    async def hors_ligne():
        raise maj.MajIndisponible("Vérification impossible : hors ligne, ou GitHub injoignable.")

    monkeypatch.setattr(maj, "derniere_release", hors_ligne)
    r = client_verrouille.get("/api/maj")
    assert r.status_code == 503
    assert "hors ligne" in r.json()["detail"]


# --- Config opt-in --------------------------------------------------------------

def test_config_maj_active_par_defaut(client):
    """La vérification au démarrage est activée par défaut (décision du
    2026-09-03 : personne ne se mettait à jour) et reste désactivable comme le
    reste de la config."""
    eff = client.get("/api/config").json()
    assert eff["maj"] == {"verification_auto": True}
    r = client.put(
        "/api/config", json={"overrides": {"maj": {"verification_auto": False}}}
    )
    assert r.json()["maj"]["verification_auto"] is False


# --- Notes, cadence, version ignorée -------------------------------------------------

NOTES_RELEASE = """## 📥 Installation

**Téléchargez le fichier `BilanOrtho-Setup-x.y.z.exe` ci-dessous.**

## ✨ Nouveautés de la version 1.10.0

- **Texte riche** dans les rubriques : gras, [listes](https://exemple.fr) et `souligné`.
- Mises à jour en un clic.
"""


def test_extraire_nouveautes():
    assert maj.extraire_nouveautes(NOTES_RELEASE) == (
        "• Texte riche dans les rubriques : gras, listes et souligné.\n• Mises à jour en un clic."
    )
    assert maj.extraire_nouveautes("") == ""
    assert maj.extraire_nouveautes("Sans section : *tout* le texte.") == "Sans section : *tout* le texte."
    assert maj.extraire_nouveautes("## Nouveautés\n" + "mot " * 1000, max_car=50).endswith("…")


def test_cadence_et_version_ignoree():
    from datetime import datetime, timedelta

    maintenant = datetime(2026, 9, 3, 12, tzinfo=UTC)
    assert maj.doit_verifier({}, maintenant)
    assert maj.doit_verifier({"derniere": "n'importe quoi"}, maintenant)
    recente = (maintenant - timedelta(hours=2)).isoformat()
    assert not maj.doit_verifier({"derniere": recente}, maintenant)
    ancienne = (maintenant - timedelta(hours=25)).isoformat()
    assert maj.doit_verifier({"derniere": ancienne}, maintenant)
    res = {"version_disponible": "2.0.0", "maj_disponible": True}
    assert maj.appliquer_etat(res, {"ignoree": "2.0.0"})["ignoree"] is True
    assert maj.appliquer_etat(res, {"ignoree": "1.9.0"})["ignoree"] is False


def test_etat_local_et_cadence_automatique(client, monkeypatch):
    """Coffre déverrouillé : la vérification automatique n'interroge GitHub
    qu'une fois par jour et mémorise le résultat ; la manuelle interroge à
    chaque fois. L'état local (info vue, version ignorée) se lit et s'écrit."""
    appels = []

    async def fausse_release():
        appels.append(1)
        return {"tag": "v99.0.0", "notes": "n", "publiee_le": "2026-09-03"}

    monkeypatch.setattr(maj, "derniere_release", fausse_release)
    assert client.get("/api/maj/etat").json() == {"info_vue": False, "ignoree": "", "derniere": ""}
    r1 = client.get("/api/maj?auto=1").json()
    r2 = client.get("/api/maj?auto=1").json()
    assert len(appels) == 1 and r1["maj_disponible"] and r2["maj_disponible"]
    assert r2["verifiee_le"] == r1["verifiee_le"]
    assert client.get("/api/maj/etat").json()["derniere"] == r1["verifiee_le"]
    client.get("/api/maj")  # manuelle : GitHub interrogé de nouveau
    assert len(appels) == 2
    # Version ignorée : plus proposée en automatique, signalée en manuel.
    etat = client.put("/api/maj/etat", json={"ignoree": "99.0.0", "info_vue": True}).json()
    assert etat["ignoree"] == "99.0.0" and etat["info_vue"] is True
    assert client.get("/api/maj?auto=1").json()["ignoree"] is True
    assert client.get("/api/maj").json()["ignoree"] is True
    assert client.put("/api/maj/etat", json={"ignoree": ""}).json()["ignoree"] == ""
    # L'état local n'est pas une surcharge de config : Paramètres ne le voit pas.
    assert "maj_etat" not in client.get("/api/config/overrides").json()


# --- Téléchargement vérifié ----------------------------------------------------------

def _cles():
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return priv, base64.b64encode(pub).decode()


# Capturé une fois : chaque simulation remplace httpx.AsyncClient, et une
# seconde simulation qui repartirait de l'attribut courant empilerait les
# transports (la première réponse simulée reviendrait toujours).
_CLIENT_REEL = httpx.AsyncClient


def _release_simulee(monkeypatch, version, exe, sommes, signature, statut_exe=200):
    """GitHub simulé : les trois fichiers d'une release, servis aux URL construites localement."""
    client_reel = _CLIENT_REEL

    def repond(requete):
        url = str(requete.url)
        if url == maj.url_asset(version, maj.NOM_SOMMES):
            return httpx.Response(200, content=sommes)
        if url == maj.url_asset(version, maj.NOM_SIGNATURE):
            return httpx.Response(200, content=signature)
        if url == maj.url_asset(version, maj.NOM_INSTALLEUR.format(version=version)):
            return httpx.Response(statut_exe, content=exe, headers={"content-length": str(len(exe))})
        return httpx.Response(404)

    def fabrique(**kwargs):
        return client_reel(transport=httpx.MockTransport(repond))

    monkeypatch.setattr(maj.httpx, "AsyncClient", fabrique)


def _signer(priv, donnees: bytes) -> bytes:
    import base64

    return base64.b64encode(priv.sign(donnees))


def _evenements(version, dossier):
    async def collecter():
        return [e async for e in maj.telecharger(version, dossier)]

    return asyncio.run(collecter())


def test_telechargement_verifie_puis_installeur_verifie(tmp_path, monkeypatch):
    import hashlib

    priv, pub = _cles()
    monkeypatch.setattr(maj, "CLE_PUBLIQUE_RELEASES", pub)
    version = "9.9.9"
    exe = b"MZ" + bytes(range(256)) * 8000  # ~2 Mo : au moins un événement de progression
    nom = maj.NOM_INSTALLEUR.format(version=version)
    sommes = f"{hashlib.sha256(exe).hexdigest()}  {nom}\n".encode()
    _release_simulee(monkeypatch, version, exe, sommes, _signer(priv, sommes))
    evts = _evenements(version, tmp_path)
    assert evts[0] == {"etape": "sommes"}
    assert any(e.get("etape") == "telechargement" and e.get("recu") for e in evts)
    assert evts[-1] == {"fini": True, "fichier": nom, "octets": len(exe)}
    assert (tmp_path / nom).read_bytes() == exe and not list(tmp_path.glob("*.part"))
    # L'installeur est connu comme vérifié ; toute altération sur disque le disqualifie.
    assert maj.fichier_verifie(version) == tmp_path / nom
    (tmp_path / nom).write_bytes(exe + b"x")
    with pytest.raises(maj.MajRefusee):
        maj.fichier_verifie(version)
    assert not (tmp_path / nom).exists()


def test_telechargement_refuse_si_signature_ou_empreinte_fausse(tmp_path, monkeypatch):
    import hashlib

    priv, pub = _cles()
    autre, _ = _cles()
    monkeypatch.setattr(maj, "CLE_PUBLIQUE_RELEASES", pub)
    version = "9.9.8"
    exe = b"MZ" * 1000
    nom = maj.NOM_INSTALLEUR.format(version=version)
    sommes = f"{hashlib.sha256(exe).hexdigest()}  {nom}\n".encode()
    # Signée par une autre clé : rien n'est téléchargé.
    _release_simulee(monkeypatch, version, exe, sommes, _signer(autre, sommes))
    evts = _evenements(version, tmp_path)
    assert "signature" in evts[-1]["erreur"] and not list(tmp_path.iterdir())
    # Bonne signature, mais le fichier servi ne correspond pas à l'empreinte.
    _release_simulee(monkeypatch, version, exe + b"altere", sommes, _signer(priv, sommes))
    evts = _evenements(version, tmp_path)
    assert "empreinte" in evts[-1]["erreur"] and not list(tmp_path.iterdir())
    assert version not in maj._VERIFIES
    # Release sans fichiers : message explicite.
    _release_simulee(monkeypatch, version, exe, sommes, _signer(priv, sommes), statut_exe=404)
    assert "publiés" in _evenements(version, tmp_path)[-1]["erreur"]
    # Sans clé embarquée (fork) : refus net, lien manuel seulement.
    monkeypatch.setattr(maj, "CLE_PUBLIQUE_RELEASES", "")
    _release_simulee(monkeypatch, version, exe, sommes, _signer(priv, sommes))
    assert "clé de publication" in _evenements(version, tmp_path)[-1]["erreur"]


def test_url_asset_contrainte():
    assert maj.url_asset("1.10.0", "SHA256SUMS").endswith("/releases/download/v1.10.0/SHA256SUMS")
    for mauvaise in ("../x", "1.10", "v1.10.0", "1.10.0/../../a", ""):
        with pytest.raises(maj.MajRefusee):
            maj.url_asset(mauvaise, "x")
    assert maj.somme_attendue("abc\n" + "a" * 64 + " *BilanOrtho-Setup-1.0.0.exe\n", "BilanOrtho-Setup-1.0.0.exe") == "a" * 64
    with pytest.raises(maj.MajRefusee):
        maj.somme_attendue("a" * 64 + "  autre.exe", "BilanOrtho-Setup-1.0.0.exe")


def test_routes_installation(client, monkeypatch, tmp_path):
    """Hors application Windows installée : 400 explicite. Dans l'app :
    sauvegarde du coffre, journal d'audit, installeur lancé avec le port."""
    r = client.post("/api/maj/telecharger", json={"version": "9.9.9"})
    assert r.status_code == 400 and "git pull" in r.json()["detail"]
    assert client.post("/api/maj/installer", json={"version": "9.9.9", "port": 8000}).status_code == 400

    monkeypatch.setattr(maj, "installation_possible", lambda: True)
    assert client.post("/api/maj/telecharger", json={"version": "../x"}).status_code == 400
    # Rien de téléchargé : 409, pas de sauvegarde, pas de lancement.
    r = client.post("/api/maj/installer", json={"version": "9.9.9", "port": 8000})
    assert r.status_code == 409 and "Téléchargez" in r.json()["detail"]

    import hashlib

    exe = tmp_path / "BilanOrtho-Setup-9.9.9.exe"
    exe.write_bytes(b"MZ")
    maj._VERIFIES["9.9.9"] = (exe, hashlib.sha256(b"MZ").hexdigest())
    lances = []
    monkeypatch.setattr(maj, "lancer_installeur", lambda chemin, port: lances.append((chemin, port)))
    r = client.post("/api/maj/installer", json={"version": "9.9.9", "port": 8003})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["lance"] is True and corps["sauvegarde"].endswith(".db")
    assert lances == [(exe, 8003)]
    assert client.get("/api/sauvegardes").json()["fichiers"]
    maj._VERIFIES.pop("9.9.9", None)


def test_lancer_installeur_arguments(tmp_path, monkeypatch):
    """Silencieux, sans redémarrage, port transmis pour la relance, journal
    dans le dossier des mises à jour ; jamais de fenêtre héritée."""
    vus = {}

    def faux_popen(args, **kw):
        vus["args"], vus["kw"] = args, kw

    monkeypatch.setattr(maj.subprocess, "Popen", faux_popen)
    monkeypatch.setattr(maj, "dossier_maj", lambda: tmp_path)
    exe = tmp_path / "BilanOrtho-Setup-1.0.0.exe"
    maj.lancer_installeur(exe, 8000)
    assert vus["args"][0] == str(exe)
    assert {"/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELANCER=8000"} <= set(vus["args"])
    assert any(a.startswith("/LOG=") and a.endswith("installeur.log") for a in vus["args"])
    assert vus["kw"]["close_fds"] is True and vus["kw"]["stdout"] == maj.subprocess.DEVNULL


def test_lanceur_reprend_le_port_demande(monkeypatch):
    import lanceur

    assert lanceur._port_demande(["--port=8003", "--sans-fenetre"]) == 8003
    assert lanceur._port_demande(["--port=abc"]) is None
    assert lanceur._port_demande([]) is None
