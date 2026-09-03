"""Base de données locale chiffrée (SQLCipher) + index vectoriel (sqlite-vec).

Toutes les données patient/bilan vivent ici, chiffrées au repos (AES-256).
L'index vectoriel du RAG « style du praticien » (Phase 4) partage la même base
chiffrée, pour une cohérence RGPD forte.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import sqlcipher3
import sqlite_vec

from . import config

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2
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

-- `signalements` : ce que les garde-fous déterministes n'ont pas retrouvé dans
-- la dictée (chiffres, noms de tests, rubrique non adossée), en JSON. Persisté
-- avec la rubrique : ces avertissements ne vivaient qu'en mémoire du
-- navigateur et disparaissaient au moindre F5 — alors qu'ils portent la
-- promesse centrale du produit.
CREATE TABLE IF NOT EXISTS section (
    id INTEGER PRIMARY KEY,
    bilan_id INTEGER REFERENCES bilan(id) ON DELETE CASCADE,
    cle TEXT,
    titre TEXT,
    ordre INTEGER,
    contenu TEXT DEFAULT '',
    statut TEXT DEFAULT 'vide',    -- vide | propose_ia | valide
    source TEXT,                   -- dictee | ia | manuel
    signalements TEXT,             -- JSON : messages « à vérifier » en attente
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
    etalonnage_type TEXT,          -- ecart_type | percentile | note_standard (moy. 10)
                                   -- | note_standard_100 (moy. 100) | age_dev
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
    -- Patient d'origine de l'extrait, quand il est connu : sans lui, un
    -- effacement RGPD laissait le texte intégral du bilan indexé — puis
    -- réinjecté dans le prompt d'un autre dossier.
    patient_id INTEGER REFERENCES patient(id) ON DELETE CASCADE,
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


def dicts(cur) -> list[dict]:
    """Lignes d'un curseur en dictionnaires {colonne: valeur}."""
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


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
        # Désactivé par défaut dans cette distribution de SQLCipher : sans
        # cela, la clé dérivée et les pages déchiffrées libérées peuvent
        # finir en swap ou dans le fichier d'hibernation — le chemin d'attaque
        # le plus réaliste sur un portable volé (revue du 2026-08-11, 5.6).
        con.execute("PRAGMA cipher_memory_security = ON")
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA foreign_keys = ON")
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
    except Exception:
        con.close()
        raise
    # Après connect() seulement : le WAL vient d'être (re)créé, et ses annexes
    # portent les mêmes données que la base.
    config.restreindre_acces(path)
    for suffixe in ("-wal", "-shm"):
        config.restreindre_acces(str(path) + suffixe)
    return con


# Tables sans lesquelles un fichier n'est pas un coffre : leur présence est
# ce qui distingue une vraie base d'un fichier vide ou tronqué.
_TABLES_ATTENDUES = ("patient", "bilan", "audit_log")


def verify(con) -> bool:
    """True si la passphrase déchiffre bien la base **et** que le schéma y est.

    Lire ``sqlite_master`` ne suffit pas : sur un fichier VIDE, SQLCipher pose
    la clé sans rien avoir à déchiffrer et la lecture réussit avec n'importe
    quelle passphrase. Une « sauvegarde » de 0 octet — copie USB interrompue,
    fichier de synchronisation en attente — passait donc la vérification qui
    précède la restauration, et écrasait le coffre courant par du vide. La
    présence des tables est le seul contrôle qui distingue les deux cas."""
    try:
        n = con.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN (?,?,?)",
            _TABLES_ATTENDUES,
        ).fetchone()[0]
    except sqlcipher3.DatabaseError:
        return False
    return n == len(_TABLES_ATTENDUES)


def init_schema(con) -> None:
    """Crée le schéma (idempotent) + la version. La table vectorielle
    ``reference_embedding`` est créée par rag.py (dimension = modèle choisi)."""
    con.executescript(_SCHEMA)
    con.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(SCHEMA_VERSION),),
    )
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    con.commit()


def _colonnes(con, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def _copie_avant_migration(con, version: int) -> Path | None:
    """Copie chiffrée du coffre, prise AVANT toute modification de schéma.

    Une migration est le seul moment où l'application réécrit la structure du
    coffre : si elle échoue à mi-chemin (coupure, disque plein), le praticien
    doit pouvoir revenir à l'état d'avant. La sauvegarde automatique, elle, ne
    tourne qu'*après* le déverrouillage — donc trop tard. La copie porte le
    numéro de version d'origine, et un échec de copie n'empêche pas la
    migration (elle reste transactionnelle) : il est seulement journalisé."""
    try:
        cible = config.data_dir() / f"coffre-avant-migration-v{version}.db"
        tmp = cible.with_suffix(".db.tmp")
        tmp.unlink(missing_ok=True)
        cible.unlink(missing_ok=True)
        con.commit()  # VACUUM refuse de tourner dans une transaction ouverte
        con.execute("VACUUM INTO ?", (str(tmp),))
        os.replace(tmp, cible)
        config.restreindre_acces(cible)
        return cible
    except Exception as exc:  # pragma: no cover - dépend du système de fichiers
        logger.warning("Copie de sécurité avant migration impossible : %s", exc)
        return None


def _migrer_v2(con) -> None:
    """v1 → v2 : deux colonnes ajoutées après l'audit du 2026-08-11.

    - `bilan_reference.patient_id` : sans ce lien, la base de style échappait à
      l'effacement RGPD — le patient exerçait son droit, l'app répondait « ok »,
      et le texte intégral de son bilan restait indexé.
    - `section.signalements` : les avertissements « à vérifier » ne vivaient
      qu'en mémoire du navigateur et disparaissaient au premier F5."""
    if "patient_id" not in _colonnes(con, "bilan_reference"):
        con.execute(
            "ALTER TABLE bilan_reference ADD COLUMN patient_id INTEGER "
            "REFERENCES patient(id) ON DELETE CASCADE"
        )
    if "signalements" not in _colonnes(con, "section"):
        con.execute("ALTER TABLE section ADD COLUMN signalements TEXT")


def migrate(con) -> None:
    """Migrations incrémentales des coffres existants (``PRAGMA user_version``).

    Appelée à chaque déverrouillage d'une base existante. Chaque évolution du
    schéma ajoute son étape ``if v < N: ... ; v = N`` — les coffres des
    utilisateurs suivent sans réinstallation.

    Deux garanties, ajoutées après l'audit du 2026-08-11 : une copie du coffre
    est prise avant la première écriture, et toutes les étapes s'appliquent
    dans **une seule transaction** — un coffre à moitié migré serait le pire
    des états."""
    v = con.execute("PRAGMA user_version").fetchone()[0]
    if v < 1:
        # Bases créées avant l'introduction du versionnage : schéma identique,
        # on estampille simplement.
        v = 1
    if v > SCHEMA_VERSION:
        raise RuntimeError(
            f"Schéma de coffre version {v} inattendu (application : {SCHEMA_VERSION}). "
            "Ce coffre a été créé par une version plus récente de l'application."
        )
    # Les tables absentes sont créées AVANT les étapes (CREATE TABLE IF NOT
    # EXISTS : sans effet sur un coffre complet). Le déverrouillage d'un coffre
    # existant ne rejoue jamais init_schema : une table apparue après la
    # création du coffre n'existait donc jamais, et une étape qui la modifie
    # (`ALTER TABLE bilan_reference`) rendait le coffre inouvrable — avec, en
    # prime, le message « espace disque insuffisant » du gestionnaire global.
    # Hors transaction : executescript commet ce qui est en attente.
    con.executescript(_SCHEMA)
    a_jour = (
        "patient_id" in _colonnes(con, "bilan_reference")
        and "signalements" in _colonnes(con, "section")
    )
    if v == SCHEMA_VERSION and a_jour:
        return  # rien à faire : ni copie ni écriture inutiles
    _copie_avant_migration(con, v)
    try:
        con.execute("BEGIN")
        if v < 2:
            _migrer_v2(con)
            v = 2
        con.execute(f"PRAGMA user_version = {v}")
        con.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(v),),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    con.commit()
