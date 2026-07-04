"""Tests de l'API HTTP (FastAPI TestClient) — hors ligne : LLM et embeddings mockés."""
from __future__ import annotations

import time

from app import config, llm, rag, security
from tests.conftest import PASSPHRASE, fake_embed

BILAN_TXT = (
    "Anamnèse\nEnfant né à terme, marche à 12 mois.\n\n"
    "Projet thérapeutique\nDeux séances par semaine."
)


# --- session / verrouillage ------------------------------------------------------

def test_statut_et_verrouillage(client):
    s = client.get("/api/status").json()
    assert s == {"db_exists": True, "unlocked": True, "first_run": False}
    assert client.post("/api/lock").status_code == 200
    assert client.get("/api/status").json()["unlocked"] is False
    # endpoint protégé -> 423
    assert client.get("/api/bilans").status_code == 423
    # mauvaise passphrase -> 401 ; bonne -> 200
    assert client.post("/api/unlock", json={"passphrase": "mauvaise"}).status_code == 401
    assert client.post("/api/unlock", json={"passphrase": PASSPHRASE}).status_code == 200
    assert client.post("/api/unlock", json={"passphrase": "  "}).status_code == 400


def test_auto_verrouillage_inactivite(client):
    client.put("/api/config", json={"overrides": {"rgpd": {"verrouillage_inactivite_minutes": 1}}})
    security._state["last_activity"] = time.monotonic() - 120
    assert client.get("/api/bilans").status_code == 423
    assert client.get("/api/status").json()["unlocked"] is False


def test_keepalive_rafraichit(client):
    assert client.post("/api/keepalive").status_code == 200


# --- config -----------------------------------------------------------------------

def test_config_get_put_delete(client):
    eff = client.get("/api/config").json()
    assert eff["llm"]["model"] == config.DEFAULTS["llm"]["model"]
    eff = client.put(
        "/api/config", json={"overrides": {"style": {"few_shot_k": 7}}}
    ).json()
    assert eff["style"]["few_shot_k"] == 7
    assert client.get("/api/config").json()["style"]["few_shot_k"] == 7
    eff = client.delete("/api/config").json()
    assert eff["style"]["few_shot_k"] == config.DEFAULTS["style"]["few_shot_k"]


def test_config_overrides_expose_les_surcharges_seules(client):
    assert client.get("/api/config/overrides").json() == {}
    client.put("/api/config", json={"overrides": {"llm": {"model": "x"}}})
    assert client.get("/api/config/overrides").json() == {"llm": {"model": "x"}}


def test_domaines_publics(client):
    doms = client.get("/api/domaines").json()
    assert {"cle": "voix", "titre": "Voix"} in doms


def test_trame_et_catalogue_configurables_via_api(client):
    client.put("/api/config", json={"overrides": {
        "trame": {"sections": [{"cle": "libre", "titre": "Rubrique libre"}]},
        "catalogues": {"voix": {"tests": [{"nom": "Échelle maison", "mesure": "m",
                                           "metriques": ["qualitatif"]}]}},
    }})
    b = client.post("/api/bilans", json={"domaines": ["voix"]}).json()
    assert [s["cle"] for s in b["sections"]] == ["libre"]
    cat = client.get("/api/catalogues/voix").json()
    assert [t["nom"] for t in cat["tests"]] == ["Échelle maison"]


def test_statut_valide_puis_envoye(client):
    bid = client.post("/api/bilans", json={"domaines": []}).json()["id"]
    b = client.put(f"/api/bilans/{bid}/statut", json={"statut": "valide"}).json()
    assert b["statut"] == "valide"
    b = client.put(
        f"/api/bilans/{bid}/statut",
        json={"statut": "envoye", "destinataire": "Dr Martin"},
    ).json()
    assert b["statut"] == "envoye"
    assert client.get("/api/bilans").json()[0]["statut"] == "envoye"
    assert client.put("/api/bilans/999/statut", json={"statut": "valide"}).status_code == 404
    # statut hors énumération -> 422 (validation Pydantic)
    assert client.put(f"/api/bilans/{bid}/statut", json={"statut": "nimporte"}).status_code == 422


# --- bilans -----------------------------------------------------------------------

def test_parcours_bilan_complet(client):
    b = client.post(
        "/api/bilans", json={"domaines": ["langage_ecrit"], "type": "initial_complexe"}
    ).json()
    bid = b["id"]
    assert [s["cle"] for s in b["sections"]][0] == "administratif"
    assert client.get("/api/bilans").json()[0]["id"] == bid
    assert client.get("/api/bilans/999").status_code == 404

    # édition + validation d'une rubrique
    r = client.put(
        f"/api/bilans/{bid}/sections/anamnese",
        json={"contenu": "Texte relu.", "statut": "valide"},
    )
    assert r.status_code == 200
    assert client.put(
        f"/api/bilans/{bid}/sections/inconnue", json={"contenu": "x"}
    ).status_code == 404

    # épreuve avec drapeau automatique
    b = client.post(f"/api/bilans/{bid}/epreuves", json={
        "test_nom": "Alouette-R", "domaine": "langage_ecrit",
        "resultats": [{"score_brut": "112", "etalonnage_type": "percentile",
                       "etalonnage_valeur": "5"}],
    }).json()
    assert b["epreuves"][0]["resultats"][0]["drapeau_seuil"] == "pathologique"

    # cotation (type complexe -> AMO 34)
    cot = client.post(f"/api/bilans/{bid}/cotation").json()
    assert cot["code_amo"] == "AMO 34" and cot["montant"] == round(34 * 2.60, 2)

    # exports
    md = client.get(f"/api/bilans/{bid}/export?format=md")
    assert "## Anamnèse" in md.text and "Texte relu." in md.text
    docx = client.get(f"/api/bilans/{bid}/export?format=docx")
    assert docx.content[:2] == b"PK"  # zip Office valide
    assert "ANAMNÈSE" in client.get(f"/api/bilans/{bid}/export?format=txt").text


def test_catalogue_par_domaine(client):
    cat = client.get("/api/catalogues/langage_ecrit").json()
    assert any(t["nom"] == "Alouette-R" for t in cat["tests"])
    # domaine inconnu -> guidance générique, pas d'erreur
    assert client.get("/api/catalogues/inconnu").json()["tests"] == []


# --- références (import + RAG) ------------------------------------------------------

def test_references_import_liste_suppression(client, mock_embed):
    r = client.post(
        "/api/references",
        files={"file": ("bilan.txt", BILAN_TXT.encode(), "text/plain")},
        data={"domaine": "langage_oral"},
    )
    assert r.status_code == 200 and r.json()["n"] == 2
    refs = client.get("/api/references").json()
    assert len(refs) == 2 and {x["section_cle"] for x in refs} == {"anamnese", "projet"}
    assert client.delete(f"/api/references/{refs[0]['id']}").status_code == 200
    assert len(client.get("/api/references").json()) == 1
    # fichier sans texte -> 400
    r = client.post("/api/references", files={"file": ("v.txt", b"  ", "text/plain")})
    assert r.status_code == 400


def test_references_embeddings_indisponibles(client, monkeypatch):
    def boom(text, cfg):
        raise rag.EmbeddingUnavailable("modèle absent")

    monkeypatch.setattr(rag, "embed", boom)
    r = client.post(
        "/api/references", files={"file": ("b.txt", BILAN_TXT.encode(), "text/plain")}
    )
    assert r.status_code == 503


# --- patients --------------------------------------------------------------------

def test_patients_api_et_cascade(client):
    assert client.post("/api/patients", json={"nom": "  "}).status_code == 400
    p = client.post("/api/patients", json={
        "nom": "Durand", "prenom": "Léa", "date_naissance": "2018-03-12", "sexe": "F",
    }).json()
    bid = client.post("/api/bilans", json={"domaines": [], "patient_id": p["id"]}).json()["id"]
    # le bilan expose l'identité ; la liste des patients compte les bilans
    assert client.get(f"/api/bilans/{bid}").json()["patient"]["nom"] == "Durand"
    assert client.get("/api/bilans").json()[0]["patient_nom"] == "Durand"
    assert client.get("/api/patients").json()[0]["nb_bilans"] == 1
    # mise à jour
    r = client.put(f"/api/patients/{p['id']}", json={"nom": "Durand", "prenom": "Léa-Marie"})
    assert r.json()["prenom"] == "Léa-Marie"
    assert client.put("/api/patients/999", json={"nom": "X"}).status_code == 404
    # effacement RGPD : le bilan rattaché disparaît
    assert client.delete(f"/api/patients/{p['id']}").status_code == 200
    assert client.get(f"/api/bilans/{bid}").status_code == 404
    assert client.delete("/api/patients/999").status_code == 404


def test_export_contient_le_patient(client):
    p = client.post("/api/patients", json={
        "nom": "Durand", "prenom": "Léa", "date_naissance": "2018-03-12",
    }).json()
    bid = client.post("/api/bilans", json={"domaines": [], "patient_id": p["id"]}).json()["id"]
    md = client.get(f"/api/bilans/{bid}/export?format=md").text
    assert "Patient : DURAND Léa, né(e) le 12/03/2018" in md


# --- sauvegarde chiffrée ------------------------------------------------------------

def test_sauvegarde_api(client):
    r = client.post("/api/sauvegarde")
    assert r.status_code == 200
    s = r.json()
    assert s["octets"] > 0 and "bilan-ortho-sauvegarde-" in s["fichier"]
    from pathlib import Path

    etat = client.get("/api/sauvegardes").json()
    assert etat["derniere"] is not None
    assert any(f["fichier"] == Path(s["fichier"]).name for f in etat["fichiers"])


# --- structuration (LLM mocké) -------------------------------------------------------

def test_structure_avec_llm_mocke(client, monkeypatch, mock_embed):
    reponse = (
        '{"updates":[{"section":"anamnese","texte":"Né à terme."},'
        '{"section":"hors_trame","texte":"écarté"}],'
        '"questions":[{"section":"anamnese","question":"Quel âge ?","pourquoi":"étalonnage"}]}'
    )
    captured = {}

    async def fake_chat_json(system, user, **kw):
        captured["system"], captured["user"] = system, user
        return reponse

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)

    # une référence importée au préalable doit nourrir le style
    client.post(
        "/api/references",
        files={"file": ("ref.txt", "Nous recevons le jeune L., très volontaire.".encode(), "text/plain")},
        data={"domaine": "langage_oral"},
    )
    bid = client.post("/api/bilans", json={"domaines": ["langage_oral"]}).json()["id"]
    r = client.post(f"/api/bilans/{bid}/structure", json={"transcription": "Il est né à terme."})
    assert r.status_code == 200
    res = r.json()
    sections = {s["cle"]: s for s in res["bilan"]["sections"]}
    assert sections["anamnese"]["contenu"] == "Né à terme."
    assert sections["anamnese"]["statut"] == "propose_ia"
    assert res["questions"] == [
        {"section": "anamnese", "question": "Quel âge ?", "pourquoi": "étalonnage"}
    ]
    # la clé hors trame a été filtrée
    assert "hors_trame" not in sections
    # le prompt contient bien l'extrait de style et les préférences
    assert "Nous recevons le jeune L." in captured["user"]
    assert "vouvoyant" in captured["user"]
    # transcription vide -> 400
    assert client.post(f"/api/bilans/{bid}/structure", json={"transcription": " "}).status_code == 400

    # prompt de structuration personnalisé : utilisé tel quel, {cles} substitué
    client.put("/api/config", json={"overrides": {
        "prompts": {"structure_system": "MON PROMPT. Clés : {cles}."}
    }})
    client.post(f"/api/bilans/{bid}/structure", json={"transcription": "Suite."})
    assert captured["system"].startswith("MON PROMPT.")
    assert "anamnese" in captured["system"]

    # avec un patient rattaché : l'âge (jamais le nom) est fourni au LLM
    p = client.post("/api/patients", json={
        "nom": "Durand", "prenom": "Léa", "date_naissance": "2018-03-12", "sexe": "F",
    }).json()
    bid2 = client.post(
        "/api/bilans", json={"domaines": ["langage_oral"], "patient_id": p["id"]}
    ).json()["id"]
    client.post(f"/api/bilans/{bid2}/structure", json={"transcription": "Elle est née à terme."})
    assert "âge à la date du bilan" in captured["user"]
    assert "sexe : F" in captured["user"] and "Ne pose PAS" in captured["user"]
    assert "Durand" not in captured["user"] and "Léa" not in captured["user"]


# --- premier lancement guidé -------------------------------------------------------

def test_installation_etat(client, monkeypatch):
    from app import systeme

    monkeypatch.setattr(systeme, "ollama_etat", lambda cfg: {"ok": True, "modeles": ["x"]})
    etat = client.get("/api/installation").json()
    assert {"ollama", "ram_gio", "proposition", "pret"} <= set(etat)
    assert etat["ollama"] is True and etat["pret"] is False


def test_installation_accessible_verrouillee(client, monkeypatch):
    """L'écran d'installation doit fonctionner avant tout déverrouillage."""
    from app import systeme

    monkeypatch.setattr(systeme, "ollama_etat", lambda cfg: {"ok": False, "modeles": []})
    client.post("/api/lock")
    assert client.get("/api/installation").status_code == 200


def test_pull_nom_invalide(client):
    assert client.post(
        "/api/installation/pull", json={"modele": "méchant; rm -rf"}
    ).status_code == 400
    assert client.post("/api/installation/pull", json={}).status_code == 400


# --- dictée ----------------------------------------------------------------------------

def test_transcribe_audio_vide(client):
    r = client.post("/api/transcribe", files={"audio": ("d.webm", b"", "audio/webm")})
    assert r.status_code == 400


def test_stt_info(client):
    info = client.get("/api/stt/info").json()
    assert {"device", "compute_type", "model"} <= set(info)
