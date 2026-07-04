"""Base de données locale chiffrée (SQLCipher) + index vectoriel (sqlite-vec).

Toutes les données patient/bilan vivent ici, chiffrées au repos (AES-256).
L'index vectoriel du RAG « style du praticien » (Phase 4) partage la même base
chiffrée, pour une cohérence RGPD forte.
"""
from __future__ import annotations

import sqlcipher3
import sqlite_vec

SCHEMA_VERSION = 1
# La table vectorielle `reference_embedding` est créée à la demande par rag.py,
# avec la dimension réelle du modèle d'embeddings choisi (nomic=768, bge-m3=1024).

# Ordre des rubriques du tronc commun réglementaire (arrêté 25/07/2023).
SECTIONS_TRONC_COMMUN: list[tuple[str, str]] = [
    ("administratif", "Objet & données administratives"),
    ("anamnese", "Anamnèse"),
    ("observations", "Observations cliniques"),
    ("epreuves", "Épreuves & résultats"),
    ("analyse", "Analyse / synthèse"),
    ("diagnostic", "Diagnostic orthophonique"),
    ("projet", "Projet thérapeutique"),
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS praticien (
    id INTEGER PRIMARY KEY,
    nom TEXT,
    rpps TEXT,
    adeli TEXT,
    email TEXT,
    telephone TEXT,
    adresse TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS patient (
    id INTEGER PRIMARY KEY,
    praticien_id INTEGER REFERENCES praticien(id),
    nom TEXT,
    prenom TEXT,
    date_naissance TEXT,
    sexe TEXT,
    telephone TEXT,
    email TEXT,
    adresse TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prescription (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER REFERENCES patient(id) ON DELETE CASCADE,
    prescripteur_nom TEXT,
    prescripteur_rpps TEXT,
    date_prescription TEXT,
    libelle TEXT,
    sans_prescription INTEGER DEFAULT 0,
    cadre_derogatoire TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bilan (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER REFERENCES patient(id) ON DELETE CASCADE,
    praticien_id INTEGER REFERENCES praticien(id),
    prescription_id INTEGER REFERENCES prescription(id),
    date_bilan TEXT,
    domaines TEXT,                 -- JSON: liste de clés de domaine
    type TEXT,                     -- initial_simple | initial_complexe | renouvellement
    statut TEXT DEFAULT 'brouillon', -- brouillon | valide | envoye
    motif TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS section (
    id INTEGER PRIMARY KEY,
    bilan_id INTEGER REFERENCES bilan(id) ON DELETE CASCADE,
    cle TEXT,
    titre TEXT,
    ordre INTEGER,
    contenu TEXT DEFAULT '',
    statut TEXT DEFAULT 'vide',    -- vide | propose_ia | valide
    source TEXT,                   -- dictee | ia | manuel
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS epreuve (
    id INTEGER PRIMARY KEY,
    bilan_id INTEGER REFERENCES bilan(id) ON DELETE CASCADE,
    domaine TEXT,
    test_nom TEXT,
    version TEXT,
    forme TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resultat (
    id INTEGER PRIMARY KEY,
    epreuve_id INTEGER REFERENCES epreuve(id) ON DELETE CASCADE,
    sous_epreuve TEXT,
    score_brut TEXT,
    etalonnage_type TEXT,          -- ecart_type | percentile | note_standard | age_dev
    etalonnage_valeur TEXT,
    percentile TEXT,
    note_standard TEXT,
    age_dev TEXT,
    interpretation TEXT,
    drapeau_seuil TEXT             -- norme | fragilite | pathologique | severe
);

CREATE TABLE IF NOT EXISTS diagnostic (
    id INTEGER PRIMARY KEY,
    bilan_id INTEGER REFERENCES bilan(id) ON DELETE CASCADE,
    texte TEXT,
    libelle_ngap TEXT,
    statut TEXT DEFAULT 'propose_ia', -- propose_ia | valide
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projet_therapeutique (
    id INTEGER PRIMARY KEY,
    bilan_id INTEGER REFERENCES bilan(id) ON DELETE CASCADE,
    objectifs TEXT,                -- JSON
    rythme TEXT,
    duree_nb_seances INTEGER,
    modalite TEXT,
    amenagements TEXT,
    examens_complementaires TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cotation (
    id INTEGER PRIMARY KEY,
    bilan_id INTEGER REFERENCES bilan(id) ON DELETE CASCADE,
    code_amo TEXT,
    coefficient REAL,
    valeur_lettre_cle REAL,
    montant REAL
);

CREATE TABLE IF NOT EXISTS envoi (
    id INTEGER PRIMARY KEY,
    bilan_id INTEGER REFERENCES bilan(id) ON DELETE CASCADE,
    destinataire TEXT,
    horodatage TEXT,
    canal TEXT,
    dmp INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS consentement (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER REFERENCES patient(id) ON DELETE CASCADE,
    type TEXT,                     -- enregistrement_vocal | traitement
    date TEXT DEFAULT (datetime('now')),
    texte TEXT,
    statut TEXT                    -- accorde | refuse
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    ts TEXT DEFAULT (datetime('now')),
    action TEXT,
    entite TEXT,
    entite_id INTEGER,
    details TEXT
);

CREATE TABLE IF NOT EXISTS bilan_reference (
    id INTEGER PRIMARY KEY,
    praticien_id INTEGER REFERENCES praticien(id),
    source TEXT,                   -- import | fictif | reglementaire
    domaine TEXT,
    section_cle TEXT,
    titre TEXT,
    texte TEXT,
    meta TEXT,                     -- JSON
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dictee (
    id INTEGER PRIMARY KEY,
    bilan_id INTEGER REFERENCES bilan(id) ON DELETE CASCADE,
    transcription TEXT,
    audio_supprime INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def connect(path, passphrase: str):
    """Ouvre une connexion SQLCipher chiffrée avec sqlite-vec chargé.

    N'exécute AUCUNE vérification de la passphrase : sur une base existante,
    une clé erronée ne lèvera qu'à la première lecture (cf. :func:`verify`).
    """
    con = sqlcipher3.connect(str(path), check_same_thread=False)
    try:
        # La passphrase est échappée (usage local mono-poste). Sur une base
        # existante, une clé erronée lève DatabaseError dès le 1er PRAGMA.
        safe = passphrase.replace("'", "''")
        con.execute(f"PRAGMA key = '{safe}'")
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA foreign_keys = ON")
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
    except Exception:
        con.close()
        raise
    return con


def verify(con) -> bool:
    """True si la passphrase déchiffre bien la base (lecture d'une table)."""
    try:
        con.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return True
    except sqlcipher3.DatabaseError:
        return False


def init_schema(con) -> None:
    """Crée le schéma (idempotent) + la version. La table vectorielle
    ``reference_embedding`` est créée par rag.py (dimension = modèle choisi)."""
    con.executescript(_SCHEMA)
    con.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(SCHEMA_VERSION),),
    )
    con.commit()
