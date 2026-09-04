"""Chemins de données avec accents, espaces et apostrophe : sous Windows,
`%LOCALAPPDATA%` porte le nom de session de la personne (« Éloïse Dupré »),
et tous les autres tests passent par un `tmp_path` ASCII."""
import pytest

from app import config, security
from tests.conftest import PASSPHRASE

NOM = "Éloïse Dupré – cabinet d'orthophonie"


@pytest.fixture()
def client_accentue(tmp_path, monkeypatch):
    dossier = tmp_path / NOM
    monkeypatch.setenv("BILAN_ORTHO_DATA_DIR", str(dossier))
    security.lock()
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.post("/api/unlock", json={"passphrase": PASSPHRASE}).status_code == 200
        yield c, dossier
    security.lock()


def test_coffre_exports_et_sauvegarde_dans_un_dossier_accentue(client_accentue):
    client, dossier = client_accentue
    assert config.db_path().parent == dossier and config.db_path().exists()
    p = client.post("/api/patients", json={"nom": "Dupré", "prenom": "Éloïse"}).json()
    bid = client.post("/api/bilans", json={"domaines": ["voix"], "patient_id": p["id"]}).json()["id"]
    for fmt, debut in (("docx", b"PK"), ("pdf", b"%PDF"), ("md", b"> **BROUILLON")):
        r = client.get(f"/api/bilans/{bid}/export", params={"format": fmt})
        assert r.status_code == 200 and r.content.startswith(debut), fmt
    # Sauvegarde chiffrée dans le dossier par défaut, sous le chemin accentué.
    s = client.post("/api/sauvegarde").json()
    assert dossier in __import__("pathlib").Path(s["fichier"]).parents
    assert client.get("/api/sauvegardes").json()["fichiers"]
    # Verrouiller puis rouvrir le même coffre.
    assert client.post("/api/lock").status_code == 200
    assert client.post("/api/unlock", json={"passphrase": PASSPHRASE}).status_code == 200
    assert client.get(f"/api/bilans/{bid}").json()["patient"]["prenom"] == "Éloïse"
