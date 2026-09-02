"""Verrouillage de l'application, journal d'audit et purge.

L'app est *verrouillée* tant que la passphrase n'a pas été fournie. Une seule
connexion chiffrée est maintenue en mémoire après déverrouillage, protégée par
un verrou (les endpoints FastAPI synchrones tournent dans un pool de threads).
La passphrase n'est jamais persistée sur le disque.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from . import config, db

logger = logging.getLogger(__name__)
_lock = threading.RLock()
_state: dict = {"con": None, "last_activity": 0.0, "minuteur": None}


class CoffreVerrouille(RuntimeError):
    """Le coffre s'est verrouillé entre la vérification d'accès et l'usage de
    la connexion (course réelle en multi-onglets via POST /api/lock). Mappée
    globalement en 423 par le serveur."""


class RestaurationImpossible(RuntimeError):
    """Demande de restauration invalide (fichier, passphrase ou version) : la
    base courante est restée intacte. Mappée en 400 par le serveur."""


def db_exists() -> bool:
    return config.db_path().exists()


def is_unlocked() -> bool:
    with _lock:
        return _state["con"] is not None


def unlock(passphrase: str, purge: bool = True) -> bool:
    """Déverrouille (ou crée au 1er lancement) la base. False si passphrase KO.

    ``purge=False`` désarme la purge RGPD pour ce seul déverrouillage : c'est
    le cas d'une base qu'on vient de restaurer (cf. :func:`restaurer`).
    """
    with _lock:
        if _state["con"] is not None:
            return True
        chemin = config.db_path()
        # Un fichier de 0 octet est un premier lancement interrompu, pas un
        # coffre : ``sqlcipher3.connect()`` crée le fichier AVANT d'y écrire
        # quoi que ce soit. Le traiter comme une base existante le rendrait
        # définitivement inouvrable maintenant que verify() exige le schéma.
        first_run = not chemin.exists() or chemin.stat().st_size == 0
        try:
            con = db.connect(chemin, passphrase)
        except Exception:
            # Base illisible : mauvaise passphrase (ou fichier corrompu).
            return False
        try:
            if first_run:
                db.init_schema(con)
            elif not db.verify(con):
                con.close()
                return False
            else:
                db.migrate(con)
        except Exception:
            # Migration/initialisation KO : fermer la connexion chiffrée avant
            # de propager, sinon elle fuit (l'app reste verrouillée).
            con.close()
            raise
        _state["con"] = con
        _state["last_activity"] = time.monotonic()
        try:
            audit("unlock", "app", None, "premier lancement" if first_run else "")
            if purge:
                _purge_conservation(con)
            con.commit()
        except Exception:
            # Échec APRÈS la pose de _state["con"] (disque plein au commit,
            # journal illisible) : le client reçoit une erreur et reste devant
            # l'écran de verrouillage, mais le coffre serait resté ouvert — un
            # simple F5 donnerait alors accès au dossier patient sans
            # passphrase. Refermer avant de propager.
            try:
                con.rollback()
            finally:
                con.close()
                _state["con"] = None
                _state["last_activity"] = 0.0
            raise
        # Hors du bloc protégé, et volontairement : une sauvegarde qui échoue
        # ne doit pas refermer un coffre correctement ouvert.
        _sauvegarde_auto(con)
        _armer_minuteur()
        return True


def lock() -> None:
    with _lock:
        _desarmer_minuteur()
        if _state["con"] is not None:
            try:
                audit("lock", "app", None, "")
                _state["con"].commit()
                _state["con"].close()
            finally:
                _state["con"] = None


def _con():
    con = _state["con"]
    if con is None:
        raise CoffreVerrouille("Application verrouillée.")
    return con


def _supprimer_sidecars(chemin) -> None:
    """Supprime les fichiers annexes WAL d'une base (``-wal``, ``-shm``).

    Un ``-wal`` orphelin rejoué à côté d'une base restaurée la corromprait."""
    for suffixe in ("-wal", "-shm"):
        Path(str(chemin) + suffixe).unlink(missing_ok=True)


def _verifier_copie(chemin: Path, passphrase: str) -> None:
    """Contrôle une copie de sauvegarde AVANT de toucher la base courante :
    ouverture avec la passphrase, lecture, version de schéma supportée."""
    illisible = RestaurationImpossible(
        "Impossible d'ouvrir cette sauvegarde avec la passphrase saisie. "
        "Vérifiez la passphrase ; si elle est correcte, le fichier est "
        "peut-être endommagé."
    )
    # Un coffre réel pèse au moins quelques pages SQLite. Refuser d'emblée le
    # fichier vide ou tronqué (copie USB interrompue, placeholder de
    # synchronisation) : sans cette borne, il est ouvrable avec N'IMPORTE
    # QUELLE passphrase, puisqu'il n'y a rien à déchiffrer.
    try:
        if chemin.stat().st_size < 4096:
            raise RestaurationImpossible(
                "Ce fichier de sauvegarde est vide ou incomplet : la copie a "
                "probablement été interrompue. Choisissez une autre sauvegarde."
            )
    except OSError:
        raise illisible
    try:
        con = db.connect(chemin, passphrase)
    except Exception:
        raise illisible
    try:
        if not db.verify(con):
            raise illisible
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version > db.SCHEMA_VERSION:
            raise RestaurationImpossible(
                "Cette sauvegarde vient d'une version plus récente de "
                "l'application. Mettez d'abord l'application à jour."
            )
    finally:
        con.close()
        # Le PRAGMA journal_mode=WAL de connect() sème -wal/-shm à côté de la
        # copie : les purger pour que l'échange ne porte que sur UN fichier.
        _supprimer_sidecars(chemin)


def restaurer(nom_fichier: str, passphrase: str) -> dict:
    """Remplace la base courante par la sauvegarde nommée, puis la rouvre.

    Toute la séquence tient sous ``_lock`` (RLock : ``lock()`` et ``unlock()``
    restent appelables depuis ce thread) — comme le VACUUM de /api/sauvegarde,
    les autres requêtes attendent ; gel borné et assumé.

    La réouverture se fait **purge désarmée**. Rejouer la purge RGPD sur une
    base qu'on vient de restaurer supprimait sur-le-champ tout ce qui y était
    plus vieux que ``conservation_jours`` — et le filet, créé avant l'échange,
    ne contient que la base de l'incident. Restaurer une sauvegarde ancienne
    la vidait donc intégralement, l'API répondant ``{"ok": true}``. Le seul
    chemin de récupération du produit ne doit pas détruire ce qu'il restaure.
    """
    from . import sauvegarde  # import tardif (évite un cycle au chargement)

    tmp = config.data_dir() / "bilan.db.restauration.tmp"
    with _lock:
        con = _con()
        cfg = config.ConfigStore(con).effective()
        try:
            src = sauvegarde.resoudre(nom_fichier, cfg)
        except ValueError as exc:
            raise RestaurationImpossible(str(exc))
        try:
            # Copier vers le dossier de données AVANT tout : os.replace n'est
            # atomique qu'au sein d'un même système de fichiers (la source
            # peut vivre sur une clé USB), et la rotation déclenchée par le
            # filet ci-dessous pourrait supprimer la sauvegarde source.
            try:
                shutil.copyfile(src, tmp)
            except OSError:
                raise RestaurationImpossible(
                    "La copie de la sauvegarde a échoué (espace disque "
                    "insuffisant ?). Libérez de l'espace puis réessayez."
                )
            _verifier_copie(tmp, passphrase)
            # Filet : la base actuelle reste récupérable depuis le dossier de
            # sauvegarde en cas de regret. (Son journal d'audit part avec elle
            # — l'entrée « restauration » vit dans la base restaurée.)
            filet = sauvegarde.creer(con, cfg)
            # Fermer la connexion (checkpoint WAL) puis purger d'éventuels
            # fichiers annexes orphelins : sous Windows, os.replace échoue sur
            # un fichier encore ouvert.
            lock()
            _supprimer_sidecars(config.db_path())
            try:
                os.replace(tmp, config.db_path())
            except OSError:
                # L'échange n'a pas eu lieu : l'ancienne base est intacte, on
                # la rouvre (best-effort) pour ne pas laisser l'app fermée.
                unlock(passphrase)
                raise RuntimeError(
                    "La restauration a échoué ; vos données actuelles sont "
                    "intactes. Réessayez, ou redémarrez l'application."
                )
            try:
                reouvert = unlock(passphrase, purge=False)
            except Exception as exc:
                raise RuntimeError(
                    "La sauvegarde a bien été restaurée, mais la réouverture "
                    "automatique a échoué. Déverrouillez l'application avec "
                    "la passphrase de la sauvegarde."
                ) from exc
            if not reouvert:
                raise RuntimeError(
                    "La sauvegarde a bien été restaurée, mais la réouverture "
                    "automatique a échoué. Déverrouillez l'application avec "
                    "la passphrase de la sauvegarde."
                )
            audit("restauration", "app", None, nom_fichier)
            _state["con"].commit()
            return {
                "ok": True,
                "fichier": nom_fichier,
                "filet": Path(filet["fichier"]).name,
            }
        finally:
            tmp.unlink(missing_ok=True)
            _supprimer_sidecars(tmp)


def touch() -> None:
    with _lock:
        _state["last_activity"] = time.monotonic()


def seconds_idle() -> float:
    with _lock:
        return time.monotonic() - _state["last_activity"]


# --- Verrouillage automatique actif ------------------------------------------
# `enforce_inactivity()` n'était appelé que par les routes protégées : sans
# requête, un coffre « verrouillé après 15 min » restait ouvert en mémoire
# indéfiniment — portable volé en veille, la clé toujours vivante dans le
# processus (revue du 2026-08-11, 5.3). Un minuteur démon vérifie donc
# l'inactivité à intervalle régulier, indépendamment de toute requête.
_MINUTEUR_INTERVALLE_S = 30.0


def _armer_minuteur() -> None:
    """Programme la prochaine vérification d'inactivité (appelé sous ``_lock``)."""
    _desarmer_minuteur()
    t = threading.Timer(_MINUTEUR_INTERVALLE_S, _tic_minuteur)
    t.daemon = True  # ne retient jamais l'arrêt du processus
    _state["minuteur"] = t
    t.start()


def _desarmer_minuteur() -> None:
    t = _state.get("minuteur")
    if t is not None:
        t.cancel()
        _state["minuteur"] = None


def _tic_minuteur() -> None:
    with _lock:
        if _state["con"] is None:
            return
        try:
            verrouille = enforce_inactivity()
        except Exception:
            logger.exception("Vérification d'inactivité impossible")
            verrouille = False
        if not verrouille and _state["con"] is not None:
            _armer_minuteur()


def enforce_inactivity() -> bool:
    """Verrouille si le délai d'inactivité configuré est dépassé. True si verrouillé.

    Tout se fait sous ``_lock`` : la connexion ne peut pas être fermée par un
    autre thread entre la vérification et la lecture (TOCTOU → 500). Le délai
    est parsé avec tolérance : une vieille surcharge mal typée (« "15" »)
    stockée avant la validation ne doit jamais bloquer les routes protégées."""
    with _lock:
        con = _state["con"]
        if con is None:
            return True
        try:
            minutes = float(
                config.ConfigStore(con).effective()["rgpd"][
                    "verrouillage_inactivite_minutes"
                ] or 0
            )
        except (KeyError, TypeError, ValueError):
            minutes = float(config.DEFAULTS["rgpd"]["verrouillage_inactivite_minutes"])
        if minutes and (time.monotonic() - _state["last_activity"]) > minutes * 60:
            lock()  # RLock : réentrant depuis ce même thread
            return True
        return False


def bilans_a_purger(con) -> list[int]:
    """Identifiants des bilans que la purge RGPD supprimerait maintenant.

    Exposé pour que l'écran Paramètres puisse annoncer le nombre de comptes
    rendus qu'une durée de conservation va détruire, AVANT de l'enregistrer :
    un compte rendu est une pièce du dossier de soins, sa suppression est
    définitive et le réglage ressemble à un simple filtre d'affichage."""
    try:
        jours = int(config.ConfigStore(con).effective()["rgpd"]["conservation_jours"])
    except (KeyError, TypeError, ValueError):
        return []
    if jours <= 0:
        return []
    return [
        r[0]
        for r in con.execute(
            "SELECT id FROM bilan WHERE updated_at < datetime('now', ?)",
            (f"-{jours} days",),
        )
    ]


def _purge_conservation(con) -> None:
    """Purge RGPD : supprime les bilans inactifs depuis plus de
    ``rgpd.conservation_jours`` jours (0 = conservation illimitée). Les
    rubriques, épreuves, résultats et dictées suivent par cascade.

    Prescriptions et identités suivent explicitement : elles sont rattachées au
    *patient*, pas au bilan, si bien que la purge détruisait le soin et gardait
    l'identité — l'inverse exact de l'effet recherché. Un patient n'est
    supprimé que s'il ne lui reste plus aucun bilan et qu'il a lui-même dépassé
    le délai de conservation (sans quoi un dossier ouvert la veille, pas encore
    documenté, partirait avec la purge)."""
    ids = bilans_a_purger(con)
    if not ids:
        return
    jours = int(config.ConfigStore(con).effective()["rgpd"]["conservation_jours"])
    trous = ",".join("?" * len(ids))  # identifiants entiers, jamais interpolés
    # Les prescriptions sont relevées avant, supprimées après : tant que le
    # bilan existe, il les référence (clé étrangère sans cascade).
    prescriptions = [
        r[0] for r in con.execute(
            f"SELECT prescription_id FROM bilan WHERE id IN ({trous}) "
            f"AND prescription_id IS NOT NULL",
            ids,
        )
    ]
    con.execute(f"DELETE FROM bilan WHERE id IN ({trous})", ids)
    if prescriptions:
        ph = ",".join("?" * len(prescriptions))
        con.execute(f"DELETE FROM prescription WHERE id IN ({ph})", prescriptions)
    orphelins = [
        r[0] for r in con.execute(
            "SELECT p.id FROM patient p "
            "LEFT JOIN bilan b ON b.patient_id = p.id "
            "WHERE b.id IS NULL AND p.created_at < datetime('now', ?)",
            (f"-{jours} days",),
        )
    ]
    for pid in orphelins:
        from . import patient as _patient

        _patient.delete(con, pid)
    # Journaliser les identifiants, pas un décompte : la suppression définitive
    # de pièces du dossier de soins doit laisser une trace de CE QUI est parti.
    audit(
        "purge_conservation", "bilan", None,
        f"{len(ids)} bilan(s) > {jours} j — n° " + ", ".join(str(i) for i in ids)
        + (f" ; {len(orphelins)} patient(s) sans bilan restant" if orphelins else ""),
    )


def _sauvegarde_auto(con) -> None:
    """Sauvegarde chiffrée automatique au déverrouillage (si due). Ne doit
    jamais empêcher le déverrouillage : best-effort — mais plus jamais
    silencieuse. Une sauvegarde qui échoue semaine après semaine sans un mot
    laisse croire à une copie de secours qui n'existe pas."""
    from . import sauvegarde  # import tardif (évite un cycle au chargement)

    try:
        cfg = config.ConfigStore(con).effective()
        res = sauvegarde.auto_si_due(con, cfg)
        if res:
            audit("sauvegarde_auto", "app", None, f"{res['octets']} octets")
        con.commit()
    except Exception as exc:
        logger.warning("Sauvegarde automatique impossible : %s", exc)
        try:
            con.rollback()
            audit("sauvegarde_auto_echec", "app", None, str(exc)[:200])
            con.commit()
        except Exception:
            pass


@contextmanager
def transaction():
    """Contexte transactionnel thread-safe sur la connexion chiffrée."""
    with _lock:
        con = _con()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise


def audit(action: str, entite: str, entite_id: int | None, details: str = "") -> None:
    """Journalise une action (traçabilité RGPD). Silencieux si verrouillé."""
    con = _state["con"]
    if con is None:
        return
    con.execute(
        "INSERT INTO audit_log(action, entite, entite_id, details) VALUES(?,?,?,?)",
        (action, entite, entite_id, details),
    )
