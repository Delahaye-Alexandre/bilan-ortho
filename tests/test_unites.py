"""Tests unitaires purs (sans base ni réseau) : config, interprétation,
cotation, découpage d'import, parsing LLM, prompts, export."""
from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from app import (
    anonymisation,
    catalogues,
    config,
    cotation,
    export,
    importer,
    llm,
    prompts,
    systeme,
    verif_chiffres,
    verif_tests,
    verif_texte,
)
from app import db as _db
from app.bilan import (
    interpret_drapeau,
    nettoyer_prefixe_titre,
    resultat_phrase,
)

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


def _odt_minimal(corps_xml: str) -> bytes:
    """Construit un .odt minimal en mémoire (zip + content.xml) : pas de
    fixture binaire dans le dépôt, et pas de dépendance à LibreOffice."""
    import io as _io
    import zipfile

    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        f"<office:body><office:text>{corps_xml}</office:text></office:body>"
        "</office:document-content>"
    )
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", content)
    return buf.getvalue()


def test_extract_text_odt():
    # Titres en text:h ET en text:p : LibreOffice produit les deux selon que
    # l'utilisateur a stylé ses titres ou non. Les blancs encodés en éléments
    # vides (text:tab, text:s) doivent redevenir des séparateurs.
    data = _odt_minimal(
        "<text:h>Anamnèse</text:h>"
        "<text:p>Enfant né à terme, marche à 12 mois.</text:p>"
        "<text:p>Épreuves et résultats</text:p>"
        "<text:p>EVALO<text:tab/>-2,1 écarts-types</text:p>"
        "<text:p>Projet thérapeutique</text:p>"
        "<text:p>Deux<text:s/>séances par semaine.</text:p>"
    )
    texte = importer.extract_text(data, "bilan.odt")
    assert "marche à 12 mois" in texte
    assert "EVALO -2,1" in texte and "Deux séances" in texte
    assert [c[0] for c in importer.sectionize(texte)] == ["anamnese", "epreuves", "projet"]


def test_extract_text_odt_corrompu():
    with pytest.raises(ValueError, match=r"\.odt illisible"):
        importer.extract_text(b"PK\x03\x04pas un odt", "bilan.odt")


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
    # un update sans texte n'apporte rien : écarté ; un update sans rubrique
    # garde son texte (section vide → remonté « non placé », jamais perdu en
    # silence — revue 2026-08-11, point 4.6) ; une question vide est écartée
    r = llm._parse_structure('{"updates":[{"section":"a"},{"texte":"b"}],"questions":[{}]}')
    assert r["updates"] == [{"section": "", "texte": "b"}]
    assert r["questions"] == []


def test_parse_structure_tolere_un_dictionnaire_au_lieu_d_une_liste():
    """`{"updates": {"anamnese": "texte"}}` (forme rendue par certains modèles
    locaux) ne doit plus lever une AttributeError → 500 opaque (point 4.6)."""
    r = llm._parse_structure('{"updates":{"anamnese":"ok"},"questions":{"x":"Âge ?"}}')
    assert r["updates"] == [{"section": "anamnese", "texte": "ok"}]
    assert r["questions"] == [{"section": "x", "question": "Âge ?", "pourquoi": ""}]
    # scalaires ou entrées non-objets : ignorés sans erreur
    assert llm._parse_structure('{"updates":"n/a","questions":[1,"a",null]}') == {
        "updates": [], "questions": [],
    }


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
    # sexe non renseigné : date introduite sans participe accordé
    assert "Patient : DURAND Léa, date de naissance : 12/03/2018 (8 ans et 3 mois à la date du bilan)" in md
    # sans patient : pas de ligne Patient
    assert "Patient :" not in _export.to_markdown(BILAN)


def test_export_accorde_la_naissance_au_sexe_enregistre():
    """Le sexe est une donnée du dossier : quand il est connu, on accorde
    plutôt que d'écrire « né(e) » ; « autre » retombe sur la forme neutre."""
    from app import export as _export

    def ligne(sexe):
        b = dict(BILAN)
        b["created_at"] = "2026-06-15 10:00:00"
        b["patient"] = {"nom": "Durand", "date_naissance": "2018-03-12", "sexe": sexe}
        return _export.to_markdown(b)

    assert "DURAND, née le 12/03/2018" in ligne("F")
    assert "DURAND, né le 12/03/2018" in ligne("M")
    assert "DURAND, date de naissance : 12/03/2018" in ligne("autre")
    assert "né(e)" not in ligne("F") + ligne("M") + ligne("autre")


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


# --- audit 2026-08-11, lot 1 : le document ne doit pas partir faux -----------

def test_cotation_ecrite_comme_sur_une_feuille_de_soins():
    """« AMO 24.0 — 62.4 € » n'est ni une notation NGAP ni un montant en euros
    français. C'est le seul chiffre du document que la CPAM peut recouper."""
    assert cotation.coeff_texte(24.0) == "24"
    assert cotation.coeff_texte(24) == "24"
    assert cotation.coeff_texte(24.5) == "24,5"
    assert cotation.euros(62.4) == "62,40 €"
    # Une cotation déjà enregistrée « AMO 24.0 » ressort corrigée à l'export.
    b = dict(BILAN, cotation=dict(BILAN["cotation"], code_amo="AMO 24.0"))
    md = export.to_markdown(b)
    assert "AMO 24 — 62,40 €" in md and "24.0" not in md


def test_export_marque_le_brouillon_dans_les_quatre_formats():
    """Un brouillon exporté était indiscernable du compte-rendu définitif."""
    brouillon = dict(BILAN, statut="brouillon")
    assert "BROUILLON" in export.to_markdown(brouillon)
    assert "BROUILLON" in export.to_txt(brouillon)
    with zipfile.ZipFile(BytesIO(export.to_docx(brouillon))) as z:
        assert "BROUILLON" in z.read("word/document.xml").decode()
    assert export.to_pdf(brouillon)  # filigrane : le PDF se génère toujours
    # Un bilan validé (ou envoyé) ne porte plus la mention.
    for statut in ("valide", "envoye"):
        assert "BROUILLON" not in export.to_markdown(dict(BILAN, statut=statut))
    # Statut absent = brouillon : un bilan jamais validé ne passe pas pour final.
    assert "BROUILLON" in export.to_markdown(BILAN)


def test_export_tableau_resiste_aux_pipes_et_retours_ligne():
    """Un « | » ou un retour à la ligne dans une interprétation cassait la
    table entière — et le .md est le format par défaut de la route."""
    b = dict(BILAN, epreuves=[{"test_nom": "Alouette-R", "resultats": [{
        "sous_epreuve": "lecture | vitesse", "score_brut": "112",
        "interpretation": "Ligne 1\nLigne 2", "drapeau_seuil": "norme",
    }]}])
    lignes = [x for x in export.to_markdown(b).splitlines() if x.startswith("|")]
    # En-tête, séparateur, une ligne de données : rien de plus.
    assert len(lignes) == 3
    assert all(x.count("|") - x.count("\\|") == 6 for x in lignes)
    assert "Ligne 1 Ligne 2" in lignes[2]
    txt = export.to_txt(b)
    assert "Ligne 1 Ligne 2" in txt


def test_export_pdf_survit_a_une_interpretation_tres_longue():
    """reportlab ne sait pas découper une cellule plus haute qu'une page :
    l'export échouait sur un commentaire clinique un peu long. Le document part
    désormais avec les résultats en lignes plutôt que refusé."""
    b = dict(BILAN, epreuves=[{"test_nom": "Alouette-R", "resultats": [{
        "sous_epreuve": "lecture", "score_brut": "112",
        "interpretation": "Commentaire clinique détaillé. " * 120,
    }]}])
    data = export.to_pdf(b)
    assert data[:4] == b"%PDF" and len(data) > 1000


def test_export_docx_est_un_zip_valide():
    data = export.to_docx(BILAN)
    with zipfile.ZipFile(BytesIO(data)) as z:
        assert "word/document.xml" in z.namelist()
        assert "Contenu A." in z.read("word/document.xml").decode()


# --- export : document réellement envoyable au prescripteur ---------------------
#
# Sans en-tête, date, destinataire ni signature, le compte-rendu devait être
# recollé à la main dans le papier à en-tête du cabinet — ce qui reprenait le
# temps que l'outil venait de faire gagner.

CFG_PRATICIEN = config._deep_merge(config.DEFAULTS, {"praticien": {
    "nom": "Martin", "prenom": "Claire", "titre": "Orthophoniste",
    "adeli": "449912345", "rpps": "10001234567",
    "adresse": "12 rue des Lilas", "code_postal": "44000", "ville": "Nantes",
    "telephone": "02 40 00 00 00", "email": "claire.martin@exemple.fr",
}})

BILAN_COMPLET = {
    **BILAN,
    "date_bilan": "2026-07-25",
    "prescripteur": {"nom": "Bernard", "rpps": "", "date": ""},
    "epreuves": [{"test_nom": "EXALANG 8-11", "resultats": [
        {"sous_epreuve": "Dictée de mots", "score_brut": "14/30",
         "etalonnage_type": "ecart_type", "etalonnage_valeur": "-2,0",
         "drapeau_seuil": "severe"},
    ]}],
}


def test_export_porte_entete_date_destinataire_et_signature():
    md = export.to_markdown(BILAN_COMPLET, CFG_PRATICIEN)
    assert "Claire Martin" in md and "Orthophoniste" in md
    assert "12 rue des Lilas, 44000 Nantes" in md
    assert "N° ADELI 449912345" in md and "RPPS 10001234567" in md
    assert "À l'attention du Dr Bernard" in md
    assert "Date du bilan : 25/07/2026" in md
    assert "Fait à Nantes, le 25/07/2026" in md


def test_export_sans_identite_naffiche_ni_entete_ni_signature():
    """Coffre neuf : aucune identité renseignée, donc aucun en-tête ni signature
    — et surtout aucune identité inventée. `titre` vaut « Orthophoniste » par
    défaut : le seul métier ne doit pas suffire à fabriquer un en-tête.

    Le destinataire, lui, vient du bilan et non de la config : il reste."""
    md = export.to_markdown(BILAN_COMPLET, config.DEFAULTS)
    assert "N° ADELI" not in md and "Fait à" not in md
    assert "Orthophoniste" not in md.split("# Compte-rendu")[0]
    assert "À l'attention du Dr Bernard" in md


def test_export_civilite_non_dupliquee():
    """« Dr Bernard » saisi tel quel ne doit pas donner « du Dr Dr Bernard »."""
    b = {**BILAN_COMPLET, "prescripteur": {"nom": "Dr Bernard"}}
    assert "À l'attention de Dr Bernard" in export.to_markdown(b, CFG_PRATICIEN)


def test_export_tableau_epreuves():
    """Les résultats saisis sont rendus en tableau, plus en lignes brutes
    collées à la prose de la rubrique."""
    md = export.to_markdown(BILAN_COMPLET, CFG_PRATICIEN)
    assert "| Test | Épreuve | Score brut | Étalonnage | Interprétation |" in md
    assert "| EXALANG 8-11 | Dictée de mots | 14/30 | -2,0 ET | déficit sévère |" in md
    txt = export.to_txt(BILAN_COMPLET, CFG_PRATICIEN)
    assert "EXALANG 8-11" in txt and "déficit sévère" in txt


def test_export_docx_contient_le_tableau():
    xml = None
    with zipfile.ZipFile(BytesIO(export.to_docx(BILAN_COMPLET, CFG_PRATICIEN))) as z:
        xml = z.read("word/document.xml").decode()
    assert "<w:tbl>" in xml and "EXALANG 8-11" in xml and "Claire Martin" in xml


def test_export_pdf_est_un_pdf_valide():
    data = export.to_pdf(BILAN_COMPLET, CFG_PRATICIEN)
    assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    assert len(data) > 1000


def test_age_calcule_a_la_date_du_bilan_pas_a_la_creation():
    """Un compte-rendu rédigé plus tard ne doit pas vieillir le patient."""
    b = {
        **BILAN_COMPLET,
        "created_at": "2026-07-25 10:00:00",
        "date_bilan": "2026-03-10",
        "patient": {"nom": "Durand", "prenom": "Chloé",
                    "date_naissance": "2017-03-14", "sexe": "F"},
    }
    md = export.to_markdown(b, CFG_PRATICIEN)
    assert "8 ans et 11 mois à la date du bilan" in md


# --- traçabilité des chiffres proposés par le LLM -------------------------------
#
# « L'IA n'invente aucun score » ne peut pas reposer sur une consigne de prompt :
# mesuré en réel, un modèle 4B transpose des écarts-types en percentiles. Ces
# tests verrouillent le garde-fou déterministe qui le rattrape.

DICTEE_REELLE = (
    "À l'Alouette, elle lit en trois minutes vingt, avec vingt-huit erreurs, ce "
    "qui lui donne un âge de lecture d'environ sept ans. À l'EXALANG 8-11, en "
    "dictée de mots je la situe à moins deux écarts-types, en dictée de phrases "
    "moins deux virgule cinq."
)


@pytest.mark.parametrize(
    "mots, attendu",
    [
        ("moins deux virgule cinq", "-2.5"),
        ("vingt-huit erreurs", "28"),
        ("quatre-vingt-douze", "92"),
        ("soixante-dix", "70"),
        ("dix-huit mois", "18"),
        ("treize mois", "13"),
    ],
)
def test_nombres_dictes_en_mots_sont_reconnus(mots, attendu):
    """La dictée énonce « moins deux », le modèle écrit « -2 » : sans cette
    conversion, tout chiffre légitime serait signalé à tort."""
    assert attendu in verif_chiffres.valeurs_numeriques(mots)


def test_texte_fidele_ne_declenche_aucun_signalement():
    fidele = ("À l'Alouette-R : 28 erreurs, âge de lecture 7 ans. "
              "EXALANG 8-11 : -2 ET et -2,5 ET.")
    assert verif_chiffres.signalements(fidele, [DICTEE_REELLE]) == []


def test_score_invente_est_signale():
    invente = "Compréhension écrite déficitaire (-1,8 écart-type)."
    assert verif_chiffres.chiffres_non_sources(invente, [DICTEE_REELLE]) == ["-1.8"]


def test_percentile_impossible_est_signale():
    """Cas observé en réel : l'écart-type dicté ressort en percentile négatif."""
    propose = "Dictée de mots : percentile (-2), dictée de phrases : percentile (-3)."
    assert verif_chiffres.percentiles_hors_bornes(propose) == ["-2", "-3"]


def test_percentile_valide_nest_pas_signale():
    assert verif_chiffres.percentiles_hors_bornes("lecture au 25e percentile") == []


def test_ecart_type_voisin_nest_pas_pris_pour_un_percentile():
    """« écart-type (-2,5) et percentile (-3) » : seul le percentile est fautif."""
    propose = "écart-type (-2,5) et percentile (-3) en dictée de phrases"
    assert verif_chiffres.percentiles_hors_bornes(propose) == ["-3"]


def test_chiffre_deja_present_dans_la_rubrique_reste_acceptable():
    """Le contenu déjà relu par le praticien fait source, comme la dictée."""
    assert verif_chiffres.chiffres_non_sources(
        "Rappelons l'âge de lecture de 7 ans.", ["âge de lecture : 7 ans"]
    ) == []


# --- audit 2026-08-11, lot 3 : pseudonymisation des bilans importés ----------

CR_REEL = """COMPTE RENDU DE BILAN ORTHOPHONIQUE

Patient : DURAND Léa, née le 12/03/2018
Adresse : 12 rue des Lilas, 44000 Nantes
Téléphone : 02 40 12 34 56 — courriel : parents.durand@example.com
N° sécurité sociale : 2 18 03 44 109 123 45
Adressé par le Dr Bernard

ANAMNÈSE
Léa est en CE1. Mme Durand rapporte des difficultés depuis la GS.
L'Alouette-R situe la lecture au 5e percentile (-2,1 ET).
"""


def test_caviardage_retire_l_identite_et_les_coordonnees():
    """Ces extraits sont relus par le modèle pendant la rédaction du bilan d'un
    AUTRE patient : le bloc d'identité ne doit pas pouvoir y revenir."""
    out, n = anonymisation.caviarder(CR_REEL)
    for fuite in ("DURAND", "Léa", "Durand", "Bernard", "12/03/2018", "Lilas",
                  "02 40 12 34 56", "parents.durand@example.com"):
        assert fuite not in out, fuite
    assert n >= 8


def test_caviardage_conserve_le_style_et_les_scores():
    """Ce que l'extrait doit transmettre — tournures, structure, façon de
    restituer un résultat — survit intact."""
    out, _ = anonymisation.caviarder(CR_REEL)
    assert "Alouette-R" in out and "5e percentile" in out and "-2,1 ET" in out
    assert "ANAMNÈSE" in out and "rapporte des difficultés" in out


def test_caviardage_suit_le_prenom_au_fil_du_texte():
    """Le prénom cité dans le corps est reconnu grâce à l'en-tête, même quand
    les deux sont traités séparément (l'en-tête étant écarté à l'import)."""
    noms = anonymisation.noms_du_document(CR_REEL)
    corps = "Léa se décourage vite ; Mme Durand s'inquiète."
    out, _ = anonymisation.caviarder(corps, noms)
    assert "Léa" not in out and "Durand" not in out


# --- audit 2026-08-11, lot 4 : noms de tests et prose non adossée -------------

NOMS_TESTS = catalogues.tous_les_noms(None)
DICTEE_BATELEM = (
    "J'ai fait l'Alouette, elle lit 112 mots. En orthographe, dictée de la "
    "Batelem, elle est au percentile cinq."
)


def test_nom_de_test_substitue_est_signale_nommement():
    """Cas reproduit deux fois sur deux : « Batelem » dicté ressort en
    « EVALEO 6-15 », nom pris dans la liste que le prompt fournit lui-même.
    L'ancien garde-fou ne voyait là que « 6 » et « -15 »."""
    propose = ("Le bilan comprend l'Alouette-R et l'EVALEO 6-15 "
               "(dictée de la Batelem au percentile cinq).")
    assert verif_tests.tests_non_sources(propose, [DICTEE_BATELEM], NOMS_TESTS) \
        == ["EVALEO 6-15"]
    assert "EVALEO 6-15" in verif_tests.signalements(
        propose, [DICTEE_BATELEM], NOMS_TESTS)[0]


def test_test_dicte_sans_son_numero_de_version_nest_pas_signale():
    """On dicte « l'Alouette », le modèle écrit « Alouette-R » : c'est
    exactement la reconnaissance que l'outil doit permettre."""
    propose = "L'épreuve Alouette-R situe la lecture au percentile 5."
    assert verif_tests.tests_non_sources(propose, [DICTEE_BATELEM], NOMS_TESTS) == []


def test_tranche_d_age_substituee_reste_visible():
    """La tolérance s'arrête au numéro de version : « EXALANG 8-11 » et
    « EXALANG 3-6 » sont deux tests différents."""
    assert verif_tests.tests_non_sources(
        "EXALANG 8-11 a été passé.", ["j'ai passé l'EXALANG 3-6"], NOMS_TESTS,
    ) == ["EXALANG 8-11"]


def test_test_sans_chiffre_dans_son_nom_est_couvert():
    """Un test purement qualitatif ne déclenchait strictement rien."""
    assert verif_tests.tests_non_sources(
        "L'évaluation perceptive GRBAS montre un grade 2.",
        ["j'ai coté la voix à l'oreille"], NOMS_TESTS,
    ) == ["GRBAS / GIRBAS"]


def test_nom_de_test_court_ne_matche_pas_un_mot_ordinaire():
    """« ELO » ne doit pas être reconnu dans « melon » ni « ELFE » dans
    « elfes » — un garde-fou bruyant finit ignoré."""
    assert verif_tests.tests_non_sources(
        "Le patient a mangé un melon et parlé des elfes.", [""], NOMS_TESTS,
    ) == []


def test_rubrique_sans_aucun_ancrage_dans_la_dictee_est_signalee():
    """Cas vérifié : une dictée sans contenu clinique produit une plainte
    entièrement inventée, qu'aucun chiffre ne trahit."""
    dictee = "euh, bonjour, je ne sais pas trop quoi dire, il fait beau aujourd'hui."
    propose = (
        "plainte actuelle : le patient rapporte des difficultés à la passation "
        "d'activités langagières, notamment lorsqu'il doit parler librement ou "
        "s'exprimer devant un groupe. Il évite ces situations et cela lui cause "
        "une certaine souffrance."
    )
    assert verif_texte.adossement(propose, [dictee]) < verif_texte.SEUIL
    assert "très peu adossée" in verif_texte.signalements(propose, [dictee])[0]


def test_redaction_fidele_nest_pas_signalee():
    """Reformuler est le travail attendu : le garde-fou ne doit pas punir une
    rédaction clinique construite à partir de la dictée."""
    dictee = ("L'Alouette-R donne un percentile 5, la lecture est lente et hachée, "
              "avec des confusions sourdes-sonores. En orthographe, nombreuses "
              "erreurs phonologiques.")
    propose = ("L'épreuve de lecture Alouette-R situe les performances au 5e "
               "percentile, ce qui traduit un déficit sévère de l'identification "
               "des mots écrits. La lecture est lente et hachée, avec des confusions "
               "entre sourdes et sonores. En orthographe, les erreurs phonologiques "
               "sont nombreuses.")
    assert verif_texte.signalements(propose, [dictee]) == []


def test_rubrique_courte_nest_pas_jugee():
    """Une phrase brève ne permet aucune mesure de recouvrement fiable."""
    assert verif_texte.adossement("Audition normale.", ["autre chose"]) is None
    assert verif_texte.signalements("Audition normale.", ["autre chose"]) == []


# --- nettoyage du « Titre : » en tête de rubrique --------------------------------

def test_prefixe_titre_retire():
    assert nettoyer_prefixe_titre("Anamnèse : Chloé, 9 ans.", "Anamnèse", "anamnese") \
        == "Chloé, 9 ans."


def test_prefixe_titre_insensible_casse_accents_et_gras():
    for brut in ["ANAMNÈSE : x", "**Anamnèse** : x", "anamnese: x", "Anamnese :  x"]:
        assert nettoyer_prefixe_titre(brut, "Anamnèse", "anamnese") == "x"


def test_prefixe_par_la_cle_de_section_retire():
    assert nettoyer_prefixe_titre("epreuves : -2 ET", "Épreuves & résultats", "epreuves") \
        == "-2 ET"


def test_contenu_clinique_avec_deux_points_est_preserve():
    """« Antécédents familiaux : … » dans l'anamnèse est du contenu, pas un titre."""
    texte = "Antécédents familiaux : le père a été suivi."
    assert nettoyer_prefixe_titre(texte, "Anamnèse", "anamnese") == texte


def test_titre_dune_autre_rubrique_est_preserve():
    """Seul le titre de LA rubrique visée est retiré : un « Observations : » mal
    routé dans les épreuves doit rester visible pour que le praticien le voie."""
    texte = "Observations cliniques : bon contact."
    assert nettoyer_prefixe_titre(texte, "Épreuves & résultats", "epreuves") == texte


# --- rattachement des clés de rubrique rendues par le LLM -----------------------
#
# Mesuré en réel contre qwen3.5:4b : le modèle écrit « euvres » au lieu de
# « epreuves » dans 5 passages sur 6. La mise à jour était alors écartée en
# SILENCE et la rubrique « Épreuves & résultats » — le cœur clinique du
# compte-rendu — disparaissait sans que rien ne le signale.

SECTIONS_REF = [{"cle": c, "titre": t} for c, t in _db.SECTIONS_TRONC_COMMUN]


@pytest.mark.parametrize(
    "brute, attendu",
    [
        ("epreuves", "epreuves"),               # exact
        ("EPREUVES", "epreuves"),               # casse
        ("anamnèse", "anamnese"),               # accents
        ("Épreuves & résultats", "epreuves"),   # titre au lieu de la clé
        ("euvres", "epreuves"),                 # corruption observée en réel
        ("diagnostique", "diagnostic"),
        ("analyse / synthèse", "analyse"),
        ("projet thérapeutique", "projet"),
        ("observation clinique", "observations"),
    ],
)
def test_cle_rubrique_rattachee(brute, attendu):
    assert llm.resoudre_cle(brute, SECTIONS_REF) == attendu


@pytest.mark.parametrize("brute", ["", "xyzzy", "toto", "cotation"])
def test_cle_rubrique_inconnue_refusee(brute):
    """Aucun rattachement au hasard : l'appelant signale au praticien plutôt
    que de ranger un texte clinique dans une rubrique arbitraire."""
    assert llm.resoudre_cle(brute, SECTIONS_REF) is None


def test_analyse_nest_jamais_confondue_avec_anamnese():
    """« analysesynthese » ressort à 0,636 de « analyse » mais 0,609 de
    « anamnese » : sans marge exigée, une analyse clinique finirait dans
    l'anamnèse du compte-rendu."""
    assert llm.resoudre_cle("analyse synthèse", SECTIONS_REF) == "analyse"
    assert llm.resoudre_cle("anamnèse", SECTIONS_REF) == "anamnese"


# --- détection d'une analyse interrompue ----------------------------------------
#
# Mesuré contre qwen3.5:4b : sur une même dictée de ~1 900 caractères, un
# passage complet propose 1 600 à 1 770 caractères, un passage amputé 620,
# parfois 106 — le compte-rendu partirait alors sans diagnostic ni projet
# thérapeutique. Ollama répond « done_reason: stop » : rien ne le trahit côté
# transport, il faut le mesurer.

DICTEE_LONGUE = "Bilan de langage écrit. " * 80   # ~1 900 caractères


def test_analyse_complete_nest_pas_signalee():
    updates = [{"texte": "x" * 1700}]
    assert llm.couverture_suspecte(DICTEE_LONGUE, updates) is False


@pytest.mark.parametrize("propose", [620, 106, 0])
def test_analyse_amputee_est_signalee(propose):
    updates = [{"texte": "x" * propose}] if propose else []
    assert llm.couverture_suspecte(DICTEE_LONGUE, updates) is True


def test_dictee_courte_ne_declenche_pas_de_faux_signal():
    """Une remarque brève remplit légitimement peu de rubriques : aucun jugement
    n'est porté en dessous du seuil de longueur."""
    assert llm.couverture_suspecte("Ajout : audition normale.", []) is False


def test_couverture_somme_toutes_les_rubriques():
    updates = [{"texte": "x" * 400}, {"texte": "y" * 400}, {"texte": "z" * 400}]
    assert llm.couverture_suspecte(DICTEE_LONGUE, updates) is False


# --- modèles Ollama hébergés (« cloud ») --------------------------------------

def test_modeles_ollama_cloud_exclus():
    """Les modèles hébergés par Ollama sur Internet (« :cloud », « -cloud »,
    ou remote_host dans /api/tags) ne sont jamais proposés : la dictée
    patient partirait chez ollama.com."""
    tags = {"models": [
        {"name": "qwen3.5:4b"},
        {"name": "glm-5.2:cloud", "remote_host": "https://ollama.com:443",
         "remote_model": "glm-5.2"},
        {"name": "gpt-oss:120b-cloud"},
        {"name": "ancien:cloud"},              # vieil Ollama, sans remote_host
        {"name": "nomic-embed-text:latest"},
    ]}
    assert systeme.modeles_locaux(tags) == ["qwen3.5:4b", "nomic-embed-text:latest"]
    assert systeme.modeles_locaux({}) == []
    assert systeme.nom_modele_cloud("glm-5.2:cloud")
    assert systeme.nom_modele_cloud("gpt-oss:120b-cloud")
    assert systeme.nom_modele_cloud(" GLM-5.2:CLOUD ")
    assert not systeme.nom_modele_cloud("qwen3.5:4b")
    assert not systeme.nom_modele_cloud("cloudy:7b")   # « cloud » n'est pas un suffixe
    assert not systeme.nom_modele_cloud("")
