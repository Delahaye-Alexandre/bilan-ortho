"""Tests sécurité réseau & configuration (audit 2026-07-17, lot 2).

- C1 : TrustedHostMiddleware — anti DNS rebinding.
- C5 : surcharges de config validées (une chaîne là où un nombre est attendu
  ne doit jamais « briquer » l'application).
- Hôtes LLM/embeddings contraints à la machine locale (RGPD).
- Politique de passphrase à la création du coffre.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import config, db
from app.main import PASSPHRASE_MIN, app
from tests.conftest import PASSPHRASE


# --- C1 : DNS rebinding -------------------------------------------------------

def test_host_etranger_rejete(client):
    r = client.get("/api/status", headers={"Host": "evil.example.com"})
    assert r.status_code == 400


def test_host_local_accepte(client):
    assert client.get("/api/status", headers={"Host": "localhost"}).status_code == 200
    assert client.get("/api/status", headers={"Host": "127.0.0.1:8000"}).status_code == 200


# --- C5 : validation des surcharges ------------------------------------------

def test_config_chaine_numerique_coercee(client):
    r = client.put("/api/config", json={
        "overrides": {"rgpd": {"verrouillage_inactivite_minutes": "15"}}
    })
    assert r.status_code == 200
    assert r.json()["rgpd"]["verrouillage_inactivite_minutes"] == 15
    # L'app reste utilisable (avant le correctif : TypeError sur toutes
    # les routes protégées, reset compris).
    assert client.get("/api/patients").status_code == 200


def test_config_valeur_invalide_rejetee(client):
    r = client.put("/api/config", json={
        "overrides": {"rgpd": {"verrouillage_inactivite_minutes": "beaucoup"}}
    })
    assert r.status_code == 422
    assert client.get("/api/patients").status_code == 200


def test_config_cles_inconnues_tolerees(client):
    """Les configurations avancées (clés non modélisées) passent toujours."""
    r = client.put("/api/config", json={
        "overrides": {"llm": {"option_future": True}, "experimental": {"x": 1}}
    })
    assert r.status_code == 200
    assert r.json()["llm"]["option_future"] is True


# --- Hôtes contraints en loopback --------------------------------------------

def test_config_host_distant_refuse(client):
    r = client.put("/api/config", json={
        "overrides": {"llm": {"host": "http://192.0.2.10:11434"}}
    })
    assert r.status_code == 422
    assert "local" in str(r.json()["detail"])
    r = client.put("/api/config", json={
        "overrides": {"embeddings": {"host": "http://exfiltration.example"}}
    })
    assert r.status_code == 422


def test_config_host_local_accepte(client):
    r = client.put("/api/config", json={
        "overrides": {"llm": {"host": "http://127.0.0.1:11434"},
                      "embeddings": {"host": "http://localhost:11434"}}
    })
    assert r.status_code == 200


def test_hote_est_local():
    assert config.hote_est_local("")
    assert config.hote_est_local("http://127.0.0.1:11434")
    assert config.hote_est_local("http://localhost:11434")
    assert config.hote_est_local("http://[::1]:11434")
    assert not config.hote_est_local("http://192.0.2.10")
    assert not config.hote_est_local("http://exfiltration.example")


# --- Passphrase ---------------------------------------------------------------

def test_passphrase_courte_refusee_a_la_creation(data_dir):
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.post("/api/unlock", json={"passphrase": "court"})
        assert r.status_code == 400
        assert str(PASSPHRASE_MIN) in r.json()["detail"]
        # Une passphrase assez longue crée bien le coffre.
        assert c.post("/api/unlock", json={"passphrase": PASSPHRASE}).status_code == 200


def test_passphrase_courte_acceptee_sur_coffre_existant(data_dir):
    """La politique s'applique à la création : un coffre historique créé avec
    une passphrase courte doit rester ouvrable."""
    con = db.connect(config.db_path(), "court")
    db.init_schema(con)
    con.close()
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.post("/api/unlock", json={"passphrase": "court"}).status_code == 200
