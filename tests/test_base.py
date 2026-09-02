"""Tests sur la base chiffrée : sécurité, config persistée, CRUD bilan, RAG."""
from __future__ import annotations

import pytest

from app import bilan, config, db, patient, rag, sauvegarde, security
from tests.conftest import PASSPHRASE, fake_vec

# --- chiffrement / verrouillage ------------------------------------------------

def test_mauvaise_passphrase_refusee(data_dir):
    assert security.unlock(PASSPHRASE) is True   # création du coffre
    security.lock()
    assert security.unlock("mauvaise") is False
    assert security.is_unlocked() is False
    assert security.unlock(PASSPHRASE) is True


def test_base_illisible_sans_cle(con, data_dir):
    con.commit()
    brut = (data_dir / "bilan.db").read_bytes()
    assert b"SQLite format 3" not in brut  # chiffrée au repos
    assert b"bilan_reference" not in brut


def test_purge_conservation(data_dir):
    assert security.unlock(PASSPHRASE)
    with security.transaction() as con:
        bid_vieux = bilan.create(con, [], "initial_simple")
        con.execute(
            "UPDATE bilan SET updated_at = datetime('now', '-40 days') WHERE id=?",
            (bid_vieux,),
        )
        bid_recent = bilan.create(con, [], "initial_simple")
        config.ConfigStore(con).set_overrides({"rgpd": {"conservation_jours": 30}})
    security.lock()
    assert security.unlock(PASSPHRASE)
    with security.transaction() as con:
        assert bilan.get(con, bid_vieux) is None          # purgé
        assert bilan.get(con, bid_recent) is not None     # conservé
        # les rubriques ont suivi par cascade
        n = con.execute("SELECT count(*) FROM section WHERE bilan_id=?", (bid_vieux,)).fetchone()[0]
        assert n == 0
        actions = [r[0] for r in con.execute("SELECT action FROM audit_log").fetchall()]
        assert "purge_conservation" in actions


def test_purge_conservation_emporte_identite_et_prescription(data_dir):
    """Audit 2026-08-11 (3.3) : la purge détruisait le soin et gardait
    l'identité — prescription et patient sont rattachés au patient, pas au
    bilan. Un patient récent sans bilan, lui, doit rester."""
    assert security.unlock(PASSPHRASE)
    with security.transaction() as con:
        pid = patient.create(con, "Durand", "Léa")
        bid = bilan.create(con, [], "initial_simple", patient_id=pid,
                           prescripteur="Bernard")
        con.execute("UPDATE bilan SET updated_at = datetime('now','-40 days') WHERE id=?", (bid,))
        con.execute("UPDATE patient SET created_at = datetime('now','-40 days') WHERE id=?", (pid,))
        # Dossier ouvert hier, pas encore documenté : ne doit pas être emporté.
        pid_neuf = patient.create(con, "Nouveau", "Cas")
        config.ConfigStore(con).set_overrides({"rgpd": {"conservation_jours": 30}})
    security.lock()
    assert security.unlock(PASSPHRASE)
    with security.transaction() as con:
        assert bilan.get(con, bid) is None
        assert patient.get(con, pid) is None
        assert patient.get(con, pid_neuf) is not None
        assert con.execute("SELECT count(*) FROM prescription").fetchone()[0] == 0


def test_effacement_patient_emporte_ses_extraits_de_style(data_dir, mock_embed):
    """Audit 2026-08-11 (3.2) : le texte intégral du bilan restait indexé après
    un effacement RGPD — puis réinjectable dans le prompt d'un autre dossier."""
    assert security.unlock(PASSPHRASE)
    with security.transaction() as con:
        pid = patient.create(con, "Durand", "Léa")
        rag.add_reference(con, None, "import", "", "anamnese", "Anamnèse",
                          "Texte du bilan de Léa.", fake_vec("x"), patient_id=pid)
        rag.add_reference(con, None, "import", "", "anamnese", "Autre",
                          "Bilan d'un patient externe.", fake_vec("y"))
        assert rag.compter_par_patient(con, pid) == 1
        assert patient.liste(con)[0]["nb_references"] == 1
        assert patient.delete(con, pid)
        restants = rag.liste(con)
        assert len(restants) == 1 and restants[0]["titre"] == "Autre"
        # L'index vectoriel suit : une table virtuelle n'a pas de cascade.
        assert con.execute(
            "SELECT count(*) FROM reference_embedding"
        ).fetchone()[0] == 1


def test_migration_v1_vers_v2_ajoute_le_rattachement(data_dir):
    """Un coffre créé avant le rattachement patient doit s'ouvrir et se migrer
    sans perte, dans une seule transaction."""
    chemin = config.db_path()
    con = db.connect(chemin, PASSPHRASE)
    db.init_schema(con)
    # On simule un coffre v1 : colonne absente, version 1.
    con.execute("DROP TABLE bilan_reference")
    con.execute(
        "CREATE TABLE bilan_reference (id INTEGER PRIMARY KEY, praticien_id INTEGER, "
        "source TEXT, domaine TEXT, section_cle TEXT, titre TEXT, texte TEXT, "
        "meta TEXT, created_at TEXT)"
    )
    con.execute("INSERT INTO bilan_reference(source, titre, texte) VALUES('import','T','Texte')")
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()

    assert security.unlock(PASSPHRASE)
    with security.transaction() as con2:
        assert con2.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        cols = {r[1] for r in con2.execute("PRAGMA table_info(bilan_reference)")}
        assert "patient_id" in cols
        assert con2.execute("SELECT texte FROM bilan_reference").fetchone()[0] == "Texte"
    # Une copie de sécurité a été prise avant d'écrire dans le coffre.
    assert (config.data_dir() / "coffre-avant-migration-v1.db").exists()


# --- config persistée -----------------------------------------------------------

def test_config_overrides_et_reset(con):
    store = config.ConfigStore(con)
    assert store.effective()["llm"]["model"] == config.DEFAULTS["llm"]["model"]
    eff = store.set_overrides({"llm": {"model": "x"}, "seuils": {"severe_et": -3.0}})
    assert eff["llm"]["model"] == "x" and eff["seuils"]["severe_et"] == -3.0
    assert eff["llm"]["temperature"] == config.DEFAULTS["llm"]["temperature"]
    # les surcharges successives fusionnent
    eff = store.set_overrides({"llm": {"temperature": 0.7}})
    assert eff["llm"]["model"] == "x" and eff["llm"]["temperature"] == 0.7
    # reset -> défauts
    assert store.reset()["llm"]["model"] == config.DEFAULTS["llm"]["model"]
    assert store.effective() == config.DEFAULTS


# --- CRUD bilan ------------------------------------------------------------------

def test_bilan_cree_la_trame_reglementaire(con):
    bid = bilan.create(con, ["langage_ecrit"], "initial_complexe")
    b = bilan.get(con, bid)
    assert [s["cle"] for s in b["sections"]] == [c for c, _ in db.SECTIONS_TRONC_COMMUN]
    assert all(s["statut"] == "vide" for s in b["sections"])
    assert b["domaine_titres"].startswith("Langage écrit")


def test_apply_updates_et_validation(con):
    bid = bilan.create(con, [], "initial_simple")
    n = bilan.apply_updates(con, bid, [
        {"section": "anamnese", "texte": "Premier jet."},
        {"section": "inexistante", "texte": "ignoré"},
    ])
    assert n == 1
    s = next(s for s in bilan.get(con, bid)["sections"] if s["cle"] == "anamnese")
    assert s["contenu"] == "Premier jet." and s["statut"] == "propose_ia"
    # un second passage s'ajoute au contenu existant
    bilan.apply_updates(con, bid, [{"section": "anamnese", "texte": "Complément."}])
    s = next(s for s in bilan.get(con, bid)["sections"] if s["cle"] == "anamnese")
    assert s["contenu"] == "Premier jet.\n\nComplément."
    # validation manuelle
    assert bilan.update_section(con, bid, "anamnese", "Version finale.", "valide")
    s = next(s for s in bilan.get(con, bid)["sections"] if s["cle"] == "anamnese")
    assert s["statut"] == "valide" and s["contenu"] == "Version finale."


def test_add_epreuve_drapeau_sans_polluer_la_rubrique(con):
    """Les résultats saisis sont stockés structurés, PAS recopiés en lignes de
    texte dans la rubrique.

    Ces lignes s'empilaient à la suite de la prose de l'IA et ressortaient
    telles quelles dans le .docx envoyé au prescripteur ; elles sont désormais
    rendues comme un tableau à l'export (cf. test_export_tableau_epreuves)."""
    bid = bilan.create(con, ["langage_ecrit"], "initial_simple")
    bilan.add_epreuve(con, bid, "langage_ecrit", "BALE", "", [{
        "sous_epreuve": "pseudo-mots", "score_brut": "12",
        "etalonnage_type": "ecart_type", "etalonnage_valeur": "-2,4",
    }], config.DEFAULTS)
    b = bilan.get(con, bid)
    assert b["epreuves"][0]["resultats"][0]["drapeau_seuil"] == "severe"
    s = next(s for s in b["sections"] if s["cle"] == "epreuves")
    assert s["contenu"] == ""


def test_trame_configurable(con):
    cfg = config._deep_merge(config.DEFAULTS, {"trame": {"sections": [
        {"cle": "intro", "titre": "Introduction"},
        {"cle": "conclusion", "titre": "Conclusion"},
        {"malforme": True},
    ]}})
    bid = bilan.create(con, [], "initial_simple", cfg=cfg)
    assert [s["cle"] for s in bilan.get(con, bid)["sections"]] == ["intro", "conclusion"]
    # trame vide ou absente -> retombe sur le tronc commun réglementaire
    bid2 = bilan.create(con, [], "initial_simple", cfg={"trame": {"sections": []}})
    assert [s["cle"] for s in bilan.get(con, bid2)["sections"]] == [
        c for c, _ in db.SECTIONS_TRONC_COMMUN
    ]


def test_patient_crud_et_effacement_rgpd(con):
    pid = patient.create(con, "Durand", "Léa", "2018-03-12", "F", "otites")
    p = patient.get(con, pid)
    assert p["nom"] == "Durand" and p["date_naissance"] == "2018-03-12"
    # rattachement de bilans + compteur
    b1 = bilan.create(con, ["langage_ecrit"], "initial_simple", patient_id=pid)
    bilan.create(con, [], "renouvellement", patient_id=pid)
    liste = patient.liste(con)
    assert liste[0]["nb_bilans"] == 2
    # le bilan expose son patient ; la liste des bilans expose le nom
    assert bilan.get(con, b1)["patient"]["prenom"] == "Léa"
    assert bilan.liste(con)[0]["patient_nom"] == "Durand"
    # mise à jour
    assert patient.update(con, pid, "Durand", "Léa-Marie", "2018-03-12", "F", "")
    assert patient.get(con, pid)["prenom"] == "Léa-Marie"
    # effacement RGPD : patient + bilans + sections en cascade
    assert patient.delete(con, pid)
    assert patient.get(con, pid) is None
    assert bilan.get(con, b1) is None
    n = con.execute("SELECT count(*) FROM section").fetchone()[0]
    assert n == 0
    assert patient.delete(con, 999) is False


# --- sauvegarde chiffrée -----------------------------------------------------------

def test_sauvegarde_creation_rotation_et_chiffrement(con, data_dir):
    cfg = config._deep_merge(config.DEFAULTS, {"sauvegarde": {"retention": 2}})
    bilan.create(con, [], "initial_simple")
    r1 = sauvegarde.creer(con, cfg)
    from pathlib import Path
    fichier = data_dir / "sauvegardes" / Path(r1["fichier"]).name
    assert fichier.exists() and r1["octets"] > 0
    # la copie reste chiffrée : aucun en-tête SQLite ni donnée en clair
    brut = fichier.read_bytes()
    assert b"SQLite format 3" not in brut and b"bilan_reference" not in brut
    # horodatage tracé
    assert con.execute(
        "SELECT value FROM meta WHERE key='derniere_sauvegarde'"
    ).fetchone() is not None
    # rotation : 3 sauvegardes, rétention 2 -> 2 fichiers restants
    sauvegarde.creer(con, cfg)
    sauvegarde.creer(con, cfg)
    fichiers = sauvegarde.liste(con, cfg)["fichiers"]
    assert len(fichiers) == 2


def test_sauvegarde_echec_sans_residu(con, data_dir):
    """Un VACUUM interrompu (disque plein…) ne laisse ni sauvegarde partielle
    qui passerait pour valide, ni fichier .tmp résiduel (BUG-12)."""
    from pathlib import Path

    import sqlcipher3

    cfg = config.DEFAULTS

    class ConVacuumKO:
        def __getattr__(self, nom):
            return getattr(con, nom)

        def execute(self, sql, params=()):
            if sql.startswith("VACUUM"):
                # simule une écriture partielle avant l'échec
                Path(params[0]).write_bytes(b"partiel")
                raise sqlcipher3.OperationalError("database or disk is full")
            return con.execute(sql, params)

    with pytest.raises(sqlcipher3.OperationalError):
        sauvegarde.creer(ConVacuumKO(), cfg)
    assert sauvegarde.liste(con, cfg)["fichiers"] == []
    assert list((data_dir / "sauvegardes").iterdir()) == []


def test_resoudre_nom_hostile_rejete(con, data_dir):
    """La restauration ne prend qu'un NOM de fichier du dossier de sauvegarde :
    chemins, préfixes étrangers, .tmp et fichiers absents sont rejetés."""
    from pathlib import Path

    cfg = config.DEFAULTS
    nom = Path(sauvegarde.creer(con, cfg)["fichier"]).name
    assert sauvegarde.resoudre(nom, cfg) == data_dir / "sauvegardes" / nom
    hostiles = [
        "../bilan.db",
        "/etc/passwd",
        "..\\bilan.db",
        "sous/" + nom,
        "autre-fichier.db",                       # préfixe étranger
        "bilan-ortho-sauvegarde-x.db.tmp",        # copie partielle
        "bilan-ortho-sauvegarde-inexistante.db",  # absent du dossier
        "",
    ]
    for nom_hostile in hostiles:
        with pytest.raises(ValueError):
            sauvegarde.resoudre(nom_hostile, cfg)


def test_statut_envoye_une_seule_trace(con):
    """Re-marquer « envoyé » un bilan déjà envoyé ne duplique pas la trace
    d'envoi (BUG-10) ; un nouveau cycle validé → envoyé en retrace une."""
    bid = bilan.create(con, [], "initial_simple")
    assert bilan.set_statut(con, bid, "envoye", "Dr Martin")
    assert bilan.set_statut(con, bid, "envoye", "Dr Martin")
    n = con.execute("SELECT COUNT(*) FROM envoi WHERE bilan_id=?", (bid,)).fetchone()[0]
    assert n == 1
    assert bilan.set_statut(con, bid, "valide")
    assert bilan.set_statut(con, bid, "envoye", "Dr Durand")
    n = con.execute("SELECT COUNT(*) FROM envoi WHERE bilan_id=?", (bid,)).fetchone()[0]
    assert n == 2


def test_sauvegarde_auto_si_due(con):
    cfg = config.DEFAULTS  # auto_jours = 7
    assert sauvegarde.auto_si_due(con, cfg) is not None   # jamais sauvegardé -> due
    assert sauvegarde.auto_si_due(con, cfg) is None       # récente -> rien
    # désactivée
    cfg0 = config._deep_merge(config.DEFAULTS, {"sauvegarde": {"auto_jours": 0}})
    con.execute("DELETE FROM meta WHERE key='derniere_sauvegarde'")
    assert sauvegarde.auto_si_due(con, cfg0) is None


def test_sauvegarde_auto_au_deverrouillage(data_dir):
    assert security.unlock(PASSPHRASE)
    dossier = data_dir / "sauvegardes"
    assert len(list(dossier.glob("bilan-ortho-sauvegarde-*.db"))) == 1
    with security.transaction() as con:
        actions = [r[0] for r in con.execute("SELECT action FROM audit_log").fetchall()]
    assert "sauvegarde_auto" in actions
    # re-déverrouillage immédiat : pas de nouvelle copie (dernière < 7 jours)
    security.lock()
    assert security.unlock(PASSPHRASE)
    assert len(list(dossier.glob("bilan-ortho-sauvegarde-*.db"))) == 1


def test_set_statut_et_envoi(con):
    bid = bilan.create(con, [], "initial_simple")
    assert bilan.set_statut(con, bid, "valide")
    assert bilan.get(con, bid)["statut"] == "valide"
    assert bilan.set_statut(con, bid, "envoye", "Dr Martin")
    assert bilan.get(con, bid)["statut"] == "envoye"
    envois = con.execute(
        "SELECT destinataire, canal FROM envoi WHERE bilan_id=?", (bid,)
    ).fetchall()
    assert envois == [("Dr Martin", "manuel")]
    assert bilan.set_statut(con, 999, "valide") is False


# --- RAG (embeddings factices) ----------------------------------------------------

def test_rag_ajout_recherche_suppression(con):
    r1 = rag.add_reference(con, None, "import", "voix", "anamnese", "A",
                           "La voix est rauque.", fake_vec("La voix est rauque."))
    rag.add_reference(con, None, "import", "langage_ecrit", "projet", "B",
                      "Deux séances par semaine.", fake_vec("Deux séances par semaine."))
    # la requête identique au texte doit remonter le bon extrait en premier
    hits = rag.retrieve(con, fake_vec("La voix est rauque."), k=1)
    assert hits and hits[0]["id"] == r1
    # filtre par domaine
    hits = rag.retrieve(con, fake_vec("La voix est rauque."), domaine="langage_ecrit", k=5)
    assert all(h["domaine"] == "langage_ecrit" for h in hits)
    # suppression : plus de référence ni de vecteur
    rag.delete(con, r1)
    assert all(h["id"] != r1 for h in rag.retrieve(con, fake_vec("La voix est rauque."), k=5))
    n_emb = con.execute("SELECT count(*) FROM reference_embedding").fetchone()[0]
    assert n_emb == len(rag.liste(con)) == 1


def test_rag_changement_de_modele_invalide_l_index(con):
    rag.add_reference(con, None, "import", "", "global", "T", "Texte.", fake_vec("Texte."))
    assert len(rag.liste(con)) == 1
    # dimension différente -> l'index et les références sont réinitialisés
    rag._ensure_table(con, 8)
    assert rag.liste(con) == []


def test_rag_vide_sans_table(con):
    assert rag.retrieve(con, fake_vec("requête")) == []
    assert rag.retrieve(con, None) == []


def test_import_decoupe_et_indexe(con):
    from app import importer

    texte = "Anamnèse\nEnfant né à terme.\n\nProjet thérapeutique\nDeux séances."
    chunks = importer.decouper(texte.encode(), "bilan.txt")
    assert {c[0] for c in chunks} == {"anamnese", "projet"}
    for cle, titre, contenu in chunks:
        rag.add_reference(con, None, "import", "langage_oral", cle, titre,
                          contenu, fake_vec(contenu))
    assert len(rag.liste(con)) == 2


def test_import_fichier_vide_leve(con):
    from app import importer

    with pytest.raises(ValueError):
        importer.decouper(b"   ", "vide.txt")


def test_pack_exemples_coherent():
    """Garde-fou du pack embarqué (data/reference) : tout fichier ajouté doit
    porter une clé de domaine connue et se découper dans le tronc commun —
    sinon « Charger les bilans d'exemple » indexerait du bruit."""
    from app import config, importer

    fichiers = importer.pack_fichiers()
    assert {d for _, d, _ in fichiers} == {d["cle"] for d in config.DOMAINES}
    tronc = {"anamnese", "observations", "epreuves", "analyse", "diagnostic", "projet"}
    for nom, _, data in fichiers:
        assert "FICTIF" in data.decode("utf-8"), f"{nom} : mention FICTIF absente"
        cles = {c[0] for c in importer.decouper(data, nom)}
        assert len(cles & tronc) >= 5, f"{nom} : rubriques détectées {cles}"


def test_fake_vec_est_stable():
    assert fake_vec("abc") == fake_vec("abc")
    assert fake_vec("abc") != fake_vec("abd")


def test_schema_versionne(con):
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_migration_base_anterieure(data_dir):
    """Un coffre créé avant le versionnage (user_version 0) est estampillé
    au déverrouillage — les évolutions futures du schéma passeront par
    db.migrate() sans réinstallation."""
    c = db.connect(config.db_path(), PASSPHRASE)
    db.init_schema(c)
    c.execute("PRAGMA user_version = 0")
    c.commit()
    c.close()
    assert security.unlock(PASSPHRASE)
    with security.transaction() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_resultat_phrase_percentile_sans_espace():
    ligne = bilan.resultat_phrase(
        "Alouette", {"etalonnage_type": "percentile", "etalonnage_valeur": "25"}
    )
    assert "25e percentile" in ligne and "25 e percentile" not in ligne


def test_seuils_percentile_configurables():
    assert bilan.interpret_drapeau("percentile", "5", config.DEFAULTS) == "pathologique"
    assert bilan.interpret_drapeau("percentile", "20", config.DEFAULTS) == "norme"
    cfg = config._deep_merge(config.DEFAULTS, {"seuils": {"fragilite_percentile": 25}})
    assert bilan.interpret_drapeau("percentile", "20", cfg) == "fragilite"


def test_update_section_rafraichit_updated_at_du_bilan(con):
    """Un bilan édité uniquement rubrique par rubrique ne doit pas être
    considéré comme inactif par la purge de conservation RGPD (audit)."""
    bid = bilan.create(con, [])
    con.execute("UPDATE bilan SET updated_at='2000-01-01 00:00:00' WHERE id=?", (bid,))
    assert bilan.update_section(con, bid, "anamnese", "Texte relu.")
    maj = con.execute("SELECT updated_at FROM bilan WHERE id=?", (bid,)).fetchone()[0]
    assert maj != "2000-01-01 00:00:00"


def test_migration_cree_les_tables_absentes_du_coffre(data_dir):
    """Un coffre v1 auquel il manque une table entière (ancienne installation,
    base reconstruite) doit s'ouvrir : la migration crée les tables manquantes
    avant ses étapes, au lieu d'échouer sur `ALTER TABLE` d'une table absente
    et de laisser le coffre définitivement inouvrable."""
    chemin = config.db_path()
    con = db.connect(chemin, PASSPHRASE)
    db.init_schema(con)
    con.execute("DROP TABLE bilan_reference")
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()

    assert security.unlock(PASSPHRASE)
    with security.transaction() as con2:
        assert con2.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        cols = {r[1] for r in con2.execute("PRAGMA table_info(bilan_reference)")}
        assert "patient_id" in cols


def test_sauvegarde_refusee_sur_support_debranche(tmp_path, monkeypatch):
    """Revue 2026-08-11, 5.4 : « /mnt/usb » reste un répertoire vide quand la
    clé est débranchée — le dossier de sauvegarde était alors créé sur le
    disque interne, et l'app annonçait des copies hors machine qui n'en sont
    jamais sorties."""
    import os
    from pathlib import Path

    racine = tmp_path / "mnt"
    (racine / "usb").mkdir(parents=True)
    monkeypatch.setattr(sauvegarde, "_RACINES_SUPPORTS", (str(racine),))
    cible = racine / "usb" / "bilan-ortho"
    cfg = {"sauvegarde": {"dossier": str(cible)}}
    with pytest.raises(sauvegarde.SupportIntrouvable):
        sauvegarde.dossier(cfg)
    assert not cible.exists()
    # Le dossier configuré est le point de montage lui-même, débranché : idem.
    with pytest.raises(sauvegarde.SupportIntrouvable):
        sauvegarde.dossier({"sauvegarde": {"dossier": str(racine / "usb")}})
    # Support monté : accepté, et le sous-dossier est créé.
    monkeypatch.setattr(os.path, "ismount", lambda p: Path(p) == racine / "usb")
    assert sauvegarde.dossier(cfg) == cible and cible.is_dir()
    # Hors des racines de supports amovibles, rien ne change : un dossier dont
    # le parent existe est créé comme avant.
    (tmp_path / "disque").mkdir()
    ailleurs = tmp_path / "disque" / "sauvegardes"
    assert sauvegarde.dossier({"sauvegarde": {"dossier": str(ailleurs)}}) == ailleurs
