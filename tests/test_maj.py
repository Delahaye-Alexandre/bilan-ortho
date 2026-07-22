"""Vérification des mises à jour : comparaison de versions et route /api/maj.

Comme le reste de la suite, tout tourne hors ligne : l'appel à l'API GitHub
(seul appel réseau externe de l'application) est systématiquement mocké.
"""
from __future__ import annotations

import asyncio

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
        httpx.Response(404, json={"message": "Not Found"}),  # aucune release publiée
        httpx.Response(200, content=b"pas du JSON"),
    ],
)
def test_derniere_version_indisponible(monkeypatch, reponse):
    _client_mocke(monkeypatch, reponse)
    with pytest.raises(maj.MajIndisponible):
        asyncio.run(maj.derniere_version())


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
        return "v99.0.0"

    monkeypatch.setattr(maj, "derniere_version", fausse_release)
    r = client_verrouille.get("/api/maj")
    assert r.status_code == 200
    corps = r.json()
    assert corps["maj_disponible"] is True
    assert corps["version_disponible"] == "99.0.0"
    assert corps["version_actuelle"] == __version__
    # L'URL ouverte par le client est construite côté serveur, jamais reprise
    # de la réponse GitHub.
    assert corps["url"] == maj.URL_TELECHARGEMENT


def test_maj_a_jour(client_verrouille, monkeypatch):
    async def fausse_release():
        return f"v{__version__}"

    monkeypatch.setattr(maj, "derniere_version", fausse_release)
    corps = client_verrouille.get("/api/maj").json()
    assert corps["maj_disponible"] is False
    assert corps["version_disponible"] == __version__


def test_maj_hors_ligne(client_verrouille, monkeypatch):
    async def hors_ligne():
        raise maj.MajIndisponible("Vérification impossible : hors ligne, ou GitHub injoignable.")

    monkeypatch.setattr(maj, "derniere_version", hors_ligne)
    r = client_verrouille.get("/api/maj")
    assert r.status_code == 503
    assert "hors ligne" in r.json()["detail"]


# --- Config opt-in --------------------------------------------------------------

def test_config_maj_opt_in(client):
    """La vérification au démarrage est désactivée par défaut (opt-in) et se
    surcharge comme le reste de la config."""
    eff = client.get("/api/config").json()
    assert eff["maj"] == {"verification_auto": False}
    r = client.put(
        "/api/config", json={"overrides": {"maj": {"verification_auto": True}}}
    )
    assert r.json()["maj"]["verification_auto"] is True
