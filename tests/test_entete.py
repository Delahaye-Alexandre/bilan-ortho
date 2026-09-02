"""En-tête du compte-rendu et suppression de l'audio de dictée (revue 2026-08-11, 9.3).

Deux chemins sans aucun test jusqu'ici, alors qu'ils portent deux promesses
fortes : le prescripteur et la date qui figurent sur un document signé
(`bilan.set_prescripteur`, `bilan.maj_entete`), et l'effacement de
l'enregistrement vocal dès la fin de la transcription (`stt.transcribe`).
"""
from __future__ import annotations

import copy
import os
import tempfile
import types
from datetime import date

import pytest

from app import bilan, config, patient, stt

# --- En-tête : prescripteur et date, persistés puis exportés -----------------

def test_prescripteur_persiste_et_une_seule_prescription_par_bilan(con):
    pid = patient.create(con, "Essai", "Zoé", "2019-02-01")
    bid = bilan.create(
        con, [], patient_id=pid, prescripteur="Dr Martin", prescripteur_rpps="10001234567",
    )
    assert bilan.prescripteur_bilan(con, bid) == {
        "nom": "Dr Martin", "rpps": "10001234567", "date": "",
    }
    # Corriger le nom garde le RPPS, corriger le RPPS garde le nom.
    assert bilan.maj_entete(con, bid, prescripteur="Dr Durand")
    assert bilan.prescripteur_bilan(con, bid)["rpps"] == "10001234567"
    assert bilan.maj_entete(con, bid, prescripteur_rpps="10009876543")
    assert bilan.prescripteur_bilan(con, bid) == {
        "nom": "Dr Durand", "rpps": "10009876543", "date": "",
    }
    # Toujours une seule ligne de prescription pour ce bilan : on remplace.
    n = con.execute(
        "SELECT count(*) FROM prescription p JOIN bilan b ON b.prescription_id = p.id "
        "WHERE b.id=?", (bid,),
    ).fetchone()[0]
    assert n == 1
    assert con.execute("SELECT count(*) FROM prescription").fetchone()[0] == 1


def test_date_du_bilan_modifiable_et_jamais_vide(con):
    bid = bilan.create(con, [])
    assert bilan.get(con, bid)["date_bilan"] == date.today().isoformat()
    assert bilan.maj_entete(con, bid, date_bilan="2026-03-01")
    assert bilan.get(con, bid)["date_bilan"] == "2026-03-01"
    # Vider la date la ramène à aujourd'hui : un compte-rendu est toujours daté.
    assert bilan.maj_entete(con, bid, date_bilan="")
    assert bilan.get(con, bid)["date_bilan"] == date.today().isoformat()
    # Bilan inconnu : rien n'est écrit, et on le dit.
    assert bilan.maj_entete(con, 424242, date_bilan="2026-03-01") is False


def test_entete_par_l_api_jusqu_au_document_exporte(client):
    b = client.post("/api/bilans", json={"domaines": []}).json()
    r = client.put(f"/api/bilans/{b['id']}", json={
        "date_bilan": "2026-03-01", "prescripteur": "Dr Martin",
        "prescripteur_rpps": "10001234567",
    })
    assert r.status_code == 200
    assert r.json()["date_bilan"] == "2026-03-01"
    assert r.json()["prescripteur"]["nom"] == "Dr Martin"
    # Le document adressé au médecin porte bien le prescripteur enregistré.
    md = client.get(f"/api/bilans/{b['id']}/export?format=md").text
    assert "Dr Martin" in md
    assert client.put("/api/bilans/424242", json={"prescripteur": "X"}).status_code == 404


# --- Dictée : l'audio est supprimé, succès ou échec -------------------------

class _FauxModele:
    def __init__(self, journal: dict, echec: Exception | None = None):
        self.journal, self.echec = journal, echec

    def transcribe(self, chemin, **kw):
        self.journal["chemin"] = chemin
        self.journal["existait_pendant"] = os.path.exists(chemin)
        self.journal["taille"] = os.path.getsize(chemin)
        if self.echec:
            raise self.echec
        segments = iter([types.SimpleNamespace(text="Bonjour "), types.SimpleNamespace(text="Zoé.")])
        return segments, types.SimpleNamespace(language="fr", duration=1.5)


@pytest.fixture()
def tmp_systeme(tmp_path, monkeypatch):
    """Répertoire temporaire système isolé : on doit pouvoir affirmer qu'il
    est vide après la transcription."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def test_transcribe_supprime_l_audio_apres_transcription(monkeypatch, tmp_systeme):
    journal: dict = {}
    monkeypatch.setattr(stt, "_get_model", lambda spec: _FauxModele(journal))
    cfg = copy.deepcopy(config.DEFAULTS)
    res = stt.transcribe(b"\x00" * 4096, "dictee.webm", cfg)
    assert res["text"] == "Bonjour Zoé." and res["duration"] == 1.5
    assert journal["existait_pendant"] and journal["taille"] == 4096
    assert journal["chemin"].endswith(".webm")
    assert not os.path.exists(journal["chemin"])
    assert list(tmp_systeme.iterdir()) == []


def test_transcribe_supprime_l_audio_meme_si_le_modele_echoue(monkeypatch, tmp_systeme):
    journal: dict = {}
    monkeypatch.setattr(
        stt, "_get_model", lambda spec: _FauxModele(journal, RuntimeError("panne")),
    )
    with pytest.raises(RuntimeError):
        stt.transcribe(b"\x00" * 10, "dictee.wav", copy.deepcopy(config.DEFAULTS))
    assert journal["existait_pendant"] and not os.path.exists(journal["chemin"])
    assert list(tmp_systeme.iterdir()) == []
