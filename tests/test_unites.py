"""Tests unitaires purs (sans base ni réseau) : config, interprétation,
cotation, découpage d'import, parsing LLM, prompts, export."""
from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from app import config, cotation, export, importer, llm, prompts
from app.bilan import interpret_drapeau, resultat_phrase

CFG = config.DEFAULTS


# --- config : fusion profonde -------------------------------------------------

def test_deep_merge_conserve_les_defauts():
    merged = config._deep_merge(CFG, {"llm": {"model": "autre"}})
    assert merged["llm"]["model"] == "autre"
    assert merged["llm"]["temperature"] == CFG["llm"]["temperature"]
    assert merged["seuils"] == CFG["seuils"]


def test_deep_merge_remplace_les_listes():
    merged = config._deep_merge(CFG, {"stt": {"hotwords": ["a"]}})
    assert merged["stt"]["hotwords"] == ["a"]


# --- interprétation d'étalonnage ---------------------------------------------

def test_drapeau_ecart_type():
    assert interpret_drapeau("ecart_type", "-0.5", CFG) == "norme"
    assert interpret_drapeau("ecart_type", "-1,2", CFG) == "fragilite"  # virgule FR
    assert interpret_drapeau("ecart_type", "-1.8", CFG) == "pathologique"
    assert interpret_drapeau("ecart_type", "-2.4", CFG) == "severe"


def test_drapeau_percentile_et_note_standard():
    assert interpret_drapeau("percentile", "50", CFG) == "norme"
    assert interpret_drapeau("percentile", "10", CFG) == "fragilite"
    assert interpret_drapeau("percentile", "5", CFG) == "pathologique"
    assert interpret_drapeau("percentile", "1", CFG) == "severe"
    # note standard : moyenne 10, ET 3 -> 4 = -2 ET
    assert interpret_drapeau("note_standard", "4", CFG) == "severe"
    assert interpret_drapeau("note_standard", "10", CFG) == "norme"


def test_drapeau_note_standard_moyenne_100():
    """Échelle moyenne 100 / ET 15 (Vineland…) : sans type dédié, une note de
    85 (= -1 ET, zone de fragilité) était lue sur l'échelle 10/3 et ressortait
    « dans la norme » — fausse réassurance dans un document médico-légal."""
    assert interpret_drapeau("note_standard_100", "100", CFG) == "norme"
    assert interpret_drapeau("note_standard_100", "85", CFG) == "fragilite"
    assert interpret_drapeau("note_standard_100", "77", CFG) == "pathologique"
    assert interpret_drapeau("note_standard_100", "70", CFG) == "severe"
    # les deux échelles restent bien distinctes
    assert interpret_drapeau("note_standard", "85", CFG) == "norme"


def test_drapeau_entree_invalide():
    assert interpret_drapeau(None, "-2", CFG) == ""
    assert interpret_drapeau("ecart_type", "abc", CFG) == ""
    assert interpret_drapeau("age_dev", "6 ans", CFG) == ""  # pas de seuil ET


def test_resultat_phrase():
    p = resultat_phrase("Alouette-R", {
        "sous_epreuve": "vitesse", "score_brut": "112",
        "etalonnage_type": "percentile", "etalonnage_valeur": "5",
        "drapeau_seuil": "pathologique",
    })
    assert "Alouette-R — vitesse" in p
    assert "score 112" in p and "sous le seuil pathologique" in p


# --- cotation NGAP -------------------------------------------------------------

def test_cotation_par_type():
    assert cotation.compute(CFG, "initial_simple")["montant"] == round(24 * 2.60, 2)
    assert cotation.compute(CFG, "initial_complexe")["code_amo"] == "AMO 34"
    assert cotation.compute(CFG, "renouvellement")["coefficient"] == 30.0
    # type inconnu -> retombe sur le bilan simple
    assert cotation.compute(CFG, "inconnu")["code_amo"] == "AMO 24"


def test_cotation_suit_la_config():
    cfg = config._deep_merge(CFG, {"cotation": {"valeur_amo": 3.0, "bilan_simple_coeff": 10}})
    assert cotation.compute(cfg, "initial_simple")["montant"] == 30.0


# --- importer : découpage par rubriques ----------------------------------------

TEXTE = """Anamnèse
Enfant né à terme, marche à 12 mois.

Épreuves et résultats
Alouette-R : 5e percentile.

Projet thérapeutique
Deux séances par semaine.
"""


def test_sectionize_decoupe_par_entetes():
    chunks = importer.sectionize(TEXTE)
    cles = [c[0] for c in chunks]
    assert cles == ["anamnese", "epreuves", "projet"]
    assert "marche à 12 mois" in chunks[0][2]


def test_sectionize_sans_entete_donne_global():
    chunks = importer.sectionize("Un texte sans aucun titre reconnaissable.")
    assert chunks[0][0] == "global"


def test_is_heading_rejette_les_phrases():
    # phrase longue / ponctuée / mot-clé au milieu -> pas un en-tête
    assert importer._is_heading("Nous détaillons ci-dessous les résultats des épreuves administrées.") is None
    assert importer._is_heading("Anamnèse:") is None
    assert importer._is_heading("Anamnèse") == "anamnese"
    assert importer._is_heading("Conclusion") == "diagnostic"


def test_extract_text_txt():
    assert "bonjour" in importer.extract_text(b"bonjour", "notes.txt")


def _pil_disponible() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(
    not (importer._ocr_available() and _pil_disponible()),
    reason="OCR (tesseract/ocrmypdf) ou Pillow absent",
)
def test_extract_text_pdf_scanne_via_ocr():
    """PDF image sans couche texte -> l'OCR (via `python -m ocrmypdf`,
    indépendant du PATH) doit récupérer le texte français."""
    import io as _io

    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28
    )
    img = Image.new("RGB", (1200, 500), "white")
    d = ImageDraw.Draw(img)
    d.text((80, 80), "Anamnèse", fill="black", font=font)
    d.text((80, 160), "Enfant adressé pour des difficultés d'articulation.", fill="black", font=font)
    buf = _io.BytesIO()
    img.save(buf, "PDF", resolution=150.0)

    texte = importer.extract_text(buf.getvalue(), "scan.pdf")
    assert "anamn" in texte.lower() and "articulation" in texte.lower()


# --- parsing LLM ---------------------------------------------------------------

def test_parse_structure_json_valide():
    raw = '{"updates":[{"section":"anamnese","texte":"ok"}],"questions":[{"section":"","question":"Âge ?","pourquoi":"étalonnage"}]}'
    r = llm._parse_structure(raw)
    assert r["updates"] == [{"section": "anamnese", "texte": "ok"}]
    assert r["questions"][0]["question"] == "Âge ?"


def test_parse_structure_json_noye_dans_du_texte():
    raw = 'Voici :\n{"updates":[{"section":"projet","texte":"x"}],"questions":[]}\nmerci'
    assert llm._parse_structure(raw)["updates"][0]["section"] == "projet"


def test_parse_structure_illisible_leve_une_erreur():
    """Une réponse non vide sans JSON lisible n'est plus un succès silencieux
    à 0 mise à jour : erreur explicite (audit BUG-11)."""
    with pytest.raises(llm.ReponseIllisible):
        llm._parse_structure("blabla sans json")
    # réponse vide : rien à signaler, résultat vide légitime
    assert llm._parse_structure("") == {"updates": [], "questions": []}
    # JSON valide avec listes vides : succès légitime (« rien à ajouter »)
    assert llm._parse_structure('{"updates":[],"questions":[]}') == {
        "updates": [], "questions": [],
    }
    # updates sans texte ou sans section sont écartés
    r = llm._parse_structure('{"updates":[{"section":"a"},{"texte":"b"}],"questions":[{}]}')
    assert r["updates"] == [] and r["questions"] == []


def test_chat_json_modele_absent(monkeypatch):
    """Un 404 d'Ollama (modèle non téléchargé) doit devenir ModeleIntrouvable,
    pas un « Ollama injoignable » trompeur (audit BUG-02)."""
    import asyncio

    import httpx

    class FauxClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return httpx.Response(
                404, request=httpx.Request("POST", url),
                text='{"error": "model not found"}',
            )

    monkeypatch.setattr(llm.httpx, "AsyncClient", FauxClient)
    with pytest.raises(llm.ModeleIntrouvable) as exc:
        asyncio.run(llm.chat_json("système", "utilisateur", model="fantome:1b"))
    assert "fantome:1b" in str(exc.value)


def test_extract_text_pdf_corrompu():
    """Les exceptions pypdf doivent devenir des ValueError (→ 400 explicite),
    pas remonter en 500 opaque (audit BUG-03)."""
    with pytest.raises(ValueError, match="PDF illisible"):
        importer.extract_text(b"%PDF-1.4 corrompu", "bilan.pdf")


# --- lanceur : décision d'ouverture du navigateur ---------------------------------

def test_lanceur_sonde_ko_nouvre_pas(data_dir, monkeypatch):
    """Serveur jamais prêt : PAS d'ouverture du navigateur sur une page morte,
    mais une boîte d'erreur qui pointe le journal serveur.log (BUG-13)."""
    import lanceur

    ouvertures, erreurs = [], []
    monkeypatch.setattr(lanceur, "_attendre_pret", lambda url, essais=240: False)
    monkeypatch.setattr(lanceur, "_ouvrir_fenetre", ouvertures.append)
    monkeypatch.setattr(lanceur, "_boite_erreur", erreurs.append)
    lanceur._ouvrir_quand_pret("http://127.0.0.1:8000")
    assert ouvertures == []
    assert len(erreurs) == 1 and "serveur.log" in erreurs[0]


def test_lanceur_sonde_ok_ouvre(monkeypatch):
    import lanceur

    ouvertures, erreurs = [], []
    monkeypatch.setattr(lanceur, "_attendre_pret", lambda url, essais=240: True)
    monkeypatch.setattr(lanceur, "_ouvrir_fenetre", ouvertures.append)
    monkeypatch.setattr(lanceur, "_boite_erreur", erreurs.append)
    lanceur._ouvrir_quand_pret("http://127.0.0.1:8000")
    assert ouvertures == ["http://127.0.0.1:8000"] and erreurs == []


# --- système : RAM, proposition de modèle, installation ---------------------------

def test_proposition_modele_par_ram():
    from app import systeme

    assert systeme.proposition_modele(32.0)["modele"] == systeme.MODELE_16GO
    assert systeme.proposition_modele(15.6)["modele"] == systeme.MODELE_16GO
    p8 = systeme.proposition_modele(8.0)
    assert p8["modele"] == systeme.MODELE_8GO and not p8["deconseille"]
    p4 = systeme.proposition_modele(4.0)
    assert p4["modele"] == systeme.MODELE_8GO and p4["deconseille"]
    # RAM indéterminable (0.0) -> proposition qualité sans avertissement
    assert systeme.proposition_modele(0.0)["modele"] == systeme.MODELE_16GO


def test_ram_totale_lisible():
    from app import systeme

    # Sur la machine de test (Linux/Windows), la lecture doit aboutir.
    assert systeme.ram_totale_gio() > 0


def test_nom_modele_valide():
    from app import systeme

    assert systeme.nom_modele_valide("qwen3.5:9b")
    assert systeme.nom_modele_valide("nomic-embed-text")
    assert not systeme.nom_modele_valide("")
    assert not systeme.nom_modele_valide("nom avec espaces")
    assert not systeme.nom_modele_valide("a" * 100)


def test_etat_installation_sans_ollama(monkeypatch):
    from app import config, systeme

    monkeypatch.setattr(systeme, "ollama_etat", lambda cfg: {"ok": False, "modeles": []})
    etat = systeme.etat_installation(config.DEFAULTS)
    assert etat["ollama"] is False and etat["pret"] is False
    assert etat["proposition"]["modele"]


def test_etat_installation_pret_via_proposition(monkeypatch):
    """Le modèle configuré (défaut) est absent mais la proposition et les
    embeddings sont installés -> prêt (l'UI basculera la config après unlock)."""
    from app import config, systeme

    prop = systeme.proposition_modele(systeme.ram_totale_gio())["modele"]
    monkeypatch.setattr(
        systeme, "ollama_etat",
        lambda cfg: {"ok": True, "modeles": [prop, "nomic-embed-text:latest"]},
    )
    etat = systeme.etat_installation(config.DEFAULTS)
    assert etat["llm_present"] is False
    assert etat["pret"] is True


# --- patient : âge & dates -------------------------------------------------------

def test_age_texte():
    from app.patient import age_texte

    assert age_texte("2018-03-12", "2026-06-15") == "8 ans et 3 mois"
    assert age_texte("2018-03-12", "2026-03-11") == "7 ans et 11 mois"  # veille d'anniversaire
    assert age_texte("2024-05-10", "2025-05-10") == "1 an"
    assert age_texte("2026-01-10", "2026-06-20") == "5 mois"
    assert age_texte("12/03/2018", "2026-06-15") == "8 ans et 3 mois"   # format FR accepté
    assert age_texte("2018-03-12", "2018-03-12 00:00:00") == "0 mois"   # créé le jour même
    assert age_texte("2030-01-01", "2026-06-15") == ""                  # future
    assert age_texte("n'importe quoi") == "" and age_texte("") == ""


def test_date_fr():
    from app.patient import date_fr

    assert date_fr("2018-03-12") == "12/03/2018"
    assert date_fr("2018-03-12 10:22:00") == "12/03/2018"
    assert date_fr("") == ""


def test_export_avec_patient():
    from app import export as _export

    b = dict(BILAN)
    b["created_at"] = "2026-06-15 10:00:00"
    b["patient"] = {"nom": "Durand", "prenom": "Léa", "date_naissance": "2018-03-12"}
    md = _export.to_markdown(b)
    assert "Patient : DURAND Léa, né(e) le 12/03/2018 (8 ans et 3 mois à la date du bilan)" in md
    # sans patient : pas de ligne Patient
    assert "Patient :" not in _export.to_markdown(BILAN)


# --- catalogues surchargés par la config ----------------------------------------

def test_catalogue_surcharge_par_config():
    from app import catalogues

    cfg = {"catalogues": {"voix": {
        "guidance": "Ma guidance à moi.",
        "tests": [{"nom": "Mon échelle maison", "mesure": "voix", "metriques": ["qualitatif"]},
                  {"pas_de_nom": True}],
    }}}
    cat = catalogues.get("voix", cfg)
    assert cat["guidance"] == "Ma guidance à moi."
    assert [t["nom"] for t in cat["tests"]] == ["Mon échelle maison"]  # entrée invalide écartée
    assert "Mon échelle maison" in catalogues.tests_noms(["voix"], cfg)
    assert "Ma guidance à moi." in catalogues.guidance(["voix"], cfg)
    # sans surcharge : catalogue intégré intact
    assert any(t["nom"] == "GRBAS / GIRBAS" for t in catalogues.get("voix")["tests"])
    # surcharge malformée ignorée
    assert catalogues.get("voix", {"catalogues": {"voix": "n'importe quoi"}})["tests"]


# --- prompts : préférences de style --------------------------------------------

def test_build_structure_user_injecte_style_et_prefs():
    msg = prompts.build_structure_user(
        "dictée", [{"cle": "anamnese", "titre": "Anamnèse", "contenu": ""}],
        "Langage écrit", style_examples=["Nous recevons le jeune L."],
        style_prefs={"niveau_detail": "concis", "vouvoiement": False},
    )
    assert "Nous recevons le jeune L." in msg
    assert "concise" in msg and "tutoyant" in msg


def test_build_structure_user_etat_reel_et_dialogue():
    sections = [
        {"cle": "anamnese", "titre": "Anamnèse", "contenu": "Né à terme. " * 200},
        {"cle": "projet", "titre": "Projet thérapeutique", "contenu": ""},
    ]
    msg = prompts.build_structure_user(
        "", sections, "Langage oral",
        reponses=[{"question": "Quel âge ?", "reponse": "7 ans", "section": "anamnese"}],
        questions_en_attente=["Le score est-il étalonné ?"],
        questions_ecartees=["Y a-t-il un suivi ORL ?"],
        questions_repondues=["Des antécédents familiaux ?"],
    )
    # contenu réel des rubriques : injecté, tronqué au-delà du plafond, vide signalé
    assert "Né à terme." in msg and "[…]" in msg and "(vide)" in msg
    coupe = msg.split("« ", 1)[1].split(" […]", 1)[0]
    assert len(coupe) <= prompts.MAX_CAR_SECTION
    # mémoire du dialogue : les trois blocs, avec le texte des questions
    assert "EN ATTENTE" in msg and "Le score est-il étalonné ?" in msg
    assert "ÉCARTÉES" in msg and "suivi ORL" in msg
    assert "DÉJÀ RÉPONDUES" in msg and "antécédents familiaux" in msg
    # réponse structurée : question + réponse + rubrique visée
    assert "Quel âge ?" in msg and "7 ans" in msg and "rubrique visée : anamnese" in msg
    # pas de dictée ce tour-ci -> pas de bloc transcription
    assert "Transcription de la dictée" not in msg


# --- export ---------------------------------------------------------------------

BILAN = {
    "type": "initial_simple",
    "domaine_titres": "Langage écrit (lecture / orthographe)",
    "sections": [
        {"titre": "Anamnèse", "contenu": "Contenu A."},
        {"titre": "Vide", "contenu": ""},
    ],
    "cotation": {"code_amo": "AMO 24", "montant": 62.4, "coefficient": 24.0,
                 "valeur_lettre_cle": 2.6},
}


def test_export_markdown_et_txt():
    md = export.to_markdown(BILAN)
    assert "# Compte-rendu de bilan orthophonique" in md
    assert "## Anamnèse" in md and "Vide" not in md
    assert "AMO 24" in md and export.DISCLAIMER in md
    txt = export.to_txt(BILAN)
    assert "ANAMNÈSE" in txt


def test_export_docx_est_un_zip_valide():
    data = export.to_docx(BILAN)
    with zipfile.ZipFile(BytesIO(data)) as z:
        assert "word/document.xml" in z.namelist()
        assert "Contenu A." in z.read("word/document.xml").decode()
