"""Fixtures partagées : base chiffrée temporaire, client API, embeddings factices.

Tous les tests tournent **hors ligne** : ni Ollama (LLM/embeddings mockés), ni
faster-whisper ne sont sollicités.
"""
from __future__ import annotations

import hashlib
import struct

import pytest

from app import config, db, rag, security

PASSPHRASE = "passphrase-de-test"
EMBED_DIM = 16


def fake_embed(text: str, cfg: dict) -> list[float]:
    """Embedding déterministe et local : hash du texte -> vecteur stable."""
    h = hashlib.sha256(text.encode()).digest()
    return [struct.unpack("<H", h[2 * i : 2 * i + 2])[0] / 65535.0 for i in range(EMBED_DIM)]


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Répertoire de données isolé + état de session remis à zéro."""
    monkeypatch.setenv("BILAN_ORTHO_DATA_DIR", str(tmp_path))
    security.lock()
    yield tmp_path
    security.lock()


@pytest.fixture()
def con(data_dir):
    """Connexion chiffrée directe (sans passer par l'API)."""
    c = db.connect(config.db_path(), PASSPHRASE)
    db.init_schema(c)
    yield c
    c.close()


@pytest.fixture()
def mock_embed(monkeypatch):
    monkeypatch.setattr(rag, "embed", fake_embed)


@pytest.fixture()
def client(data_dir, monkeypatch):
    """Client HTTP de test, coffre créé et déverrouillé."""
    from fastapi.testclient import TestClient

    from app.main import app

    # base_url 127.0.0.1 : le TrustedHostMiddleware (anti DNS rebinding)
    # rejette tout autre en-tête Host, y compris le « testserver » par défaut.
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.post("/api/unlock", json={"passphrase": PASSPHRASE})
        assert r.status_code == 200
        yield c
