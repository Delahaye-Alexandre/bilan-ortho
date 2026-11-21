"""Borne de durée de la dictée côté serveur (`rgpd.dictee_max_minutes`) : la
limite n'existait que dans le navigateur (arrêt automatique du micro)."""
import copy
import os
import types
import wave

import pytest

from app import config, stt


class _Modele:
    def __init__(self, duree: float, journal: dict):
        self.duree, self.journal = duree, journal

    def transcribe(self, chemin, **kw):
        self.journal["appels"] = self.journal.get("appels", 0) + 1
        self.journal["chemin"] = chemin
        return iter([types.SimpleNamespace(text="Texte long.")]), types.SimpleNamespace(
            language="fr", duration=self.duree
        )


def cfg_avec(max_minutes) -> dict:
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["rgpd"]["dictee_max_minutes"] = max_minutes
    return cfg


def test_duree_mesuree_par_le_modele_au_dela_de_la_borne(monkeypatch):
    journal: dict = {}
    monkeypatch.setattr(stt, "_get_model", lambda spec: _Modele(31 * 60, journal))
    monkeypatch.setattr(stt, "_duree_audio", lambda chemin: None)  # conteneur muet
    with pytest.raises(stt.DicteeTropLongue) as exc:
        stt.transcribe(b"\x00" * 100, "dictee.webm", cfg_avec(30))
    assert "31 min" in str(exc.value) and "30 min" in str(exc.value)
    assert journal["appels"] == 1 and not os.path.exists(journal["chemin"])  # audio purgé


def test_tolerance_de_quelques_secondes_apres_l_arret_automatique(monkeypatch):
    monkeypatch.setattr(stt, "_get_model", lambda spec: _Modele(30 * 60 + 4, {}))
    monkeypatch.setattr(stt, "_duree_audio", lambda chemin: None)
    assert stt.transcribe(b"\x00" * 100, "d.webm", cfg_avec(30))["text"] == "Texte long."


def test_duree_annoncee_par_le_conteneur_refusee_avant_la_transcription(monkeypatch):
    journal: dict = {}
    monkeypatch.setattr(stt, "_get_model", lambda spec: _Modele(5, journal))
    monkeypatch.setattr(stt, "_duree_audio", lambda chemin: 45 * 60.0)
    with pytest.raises(stt.DicteeTropLongue):
        stt.transcribe(b"\x00" * 100, "d.wav", cfg_avec(10))
    assert "appels" not in journal  # rien transcrit : pas de calcul pour rien


def test_sans_borne_ni_duree_rien_ne_change(monkeypatch):
    monkeypatch.setattr(stt, "_get_model", lambda spec: _Modele(3 * 3600, {}))
    monkeypatch.setattr(stt, "_duree_audio", lambda chemin: 3 * 3600.0)
    assert stt.transcribe(b"\x00" * 100, "d.wav", cfg_avec(0))["duration"] == 3 * 3600


def test_duree_du_conteneur_lue_ou_inconnue(tmp_path):
    # Un fichier qui n'est pas un conteneur décodable : durée inconnue, pas d'erreur.
    assert stt._duree_audio(os.devnull) is None
    # Un vrai WAV d'une seconde et demie : durée lue avant toute transcription.
    chemin = tmp_path / "silence.wav"
    with wave.open(str(chemin), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 24000)
    assert abs(stt._duree_audio(str(chemin)) - 1.5) < 0.05


def test_api_transcribe_dictee_trop_longue_400(client, monkeypatch):
    monkeypatch.setattr(stt, "_get_model", lambda spec: _Modele(40 * 60, {}))
    monkeypatch.setattr(stt, "_duree_audio", lambda chemin: None)
    r = client.post("/api/transcribe", files={"audio": ("d.webm", b"\x00" * 100, "audio/webm")})
    assert r.status_code == 400 and "Dictée trop longue" in r.json()["detail"]
    assert "Paramètres" in r.json()["detail"]


def test_modele_charge_depuis_le_cache_sans_reseau(monkeypatch):
    """faster-whisper interroge Hugging Face à chaque chargement si on ne lui
    demande pas le cache seul : une requête sortante par lancement, alors que
    la documentation promet « seul GitHub ». Le réseau ne sert que si le
    modèle manque."""
    import faster_whisper

    from app import stt

    appels = []

    class Faux:
        def __init__(self, nom, **reglages):
            appels.append(reglages.get("local_files_only", False))
            if reglages.get("local_files_only") and absent["oui"]:
                raise RuntimeError("modèle absent du cache")

    absent = {"oui": False}
    monkeypatch.setattr(faster_whisper, "WhisperModel", Faux)
    monkeypatch.setattr(stt, "_cache", {"model": None, "spec": None})
    spec = {"model": "medium", "device": "cpu", "compute_type": "int8"}
    stt._get_model(spec)
    assert appels == [True]  # présent : aucun appel au réseau
    absent["oui"] = True
    monkeypatch.setattr(stt, "_cache", {"model": None, "spec": None})
    stt._get_model(spec)
    assert appels == [True, True, False]  # absent : téléchargement, comme avant


def test_mots_cles_courts_et_tests_du_domaine():
    """Les 41 termes génériques doublaient le temps de transcription (mesuré) :
    la liste transmise reste courte et porte les tests du domaine du bilan."""
    import copy

    from app import config, stt

    cfg = copy.deepcopy(config.DEFAULTS)
    assert len(stt.mots_cles(cfg)) < 80
    cfg["stt"]["tests_bilan"] = ["Alouette-R", "BALE", "écart-type"]
    assert stt.mots_cles(cfg).endswith("Alouette-R, BALE")  # sans doublon
    # Une configuration qui porte encore l'ancienne liste générique suit le défaut.
    cfg["stt"]["hotwords"] = sorted(stt.ANCIENS_MOTS_CLES)
    assert stt.mots_cles(cfg).startswith("écart-type, percentile")
    # La liste de l'orthophoniste passe d'abord ; l'ensemble est borné.
    cfg["stt"]["hotwords"] = ["Batelem"]
    cfg["stt"]["tests_bilan"] = [f"Test numéro {i}" for i in range(60)]
    mots = stt.mots_cles(cfg)
    assert mots.startswith("Batelem, Test numéro 0") and len(mots) <= 220
    cfg["stt"]["hotwords"], cfg["stt"]["tests_bilan"] = [], []
    assert stt.mots_cles(cfg) is None
