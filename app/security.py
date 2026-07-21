"""Verrouillage de l'application, journal d'audit et purge.

L'app est *verrouillée* tant que la passphrase n'a pas été fournie. Une seule
connexion chiffrée est maintenue en mémoire après déverrouillage, protégée par
un verrou (les endpoints FastAPI synchrones tournent dans un pool de threads).
La passphrase n'est jamais persistée sur le disque.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager

from . import config, db

_lock = threading.RLock()
_state: dict = {"con": None, "last_activity": 0.0}


class CoffreVerrouille(RuntimeError):
    """Le coffre s'est verrouillé entre la vérification d'accès et l'usage de
    la connexion (course réelle en multi-onglets via POST /api/lock). Mappée
    globalement en 423 par le serveur."""


def db_exists() -> bool:
    return config.db_path().exists()


def is_unlocked() -> bool:
    with _lock:
        return _state["con"] is not None


def unlock(passphrase: str) -> bool:
    """Déverrouille (ou crée au 1er lancement) la base. False si passphrase KO."""
    with _lock:
        if _state["con"] is not None:
            return True
        first_run = not db_exists()
        try:
            con = db.connect(config.db_path(), passphrase)
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
        audit("unlock", "app", None, "premier lancement" if first_run else "")
        _purge_conservation(con)
        _sauvegarde_auto(con)
        con.commit()
        return True


def lock() -> None:
    with _lock:
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


def touch() -> None:
    with _lock:
        _state["last_activity"] = time.monotonic()


def seconds_idle() -> float:
    with _lock:
        return time.monotonic() - _state["last_activity"]


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


def _purge_conservation(con) -> None:
    """Purge RGPD : supprime les bilans inactifs depuis plus de
    ``rgpd.conservation_jours`` jours (0 = conservation illimitée). Les
    rubriques, épreuves, résultats et dictées suivent par cascade."""
    try:
        jours = int(config.ConfigStore(con).effective()["rgpd"]["conservation_jours"])
    except (KeyError, TypeError, ValueError):
        return
    if jours <= 0:
        return
    cur = con.execute(
        "DELETE FROM bilan WHERE updated_at < datetime('now', ?)",
        (f"-{jours} days",),
    )
    if cur.rowcount:
        audit("purge_conservation", "bilan", None, f"{cur.rowcount} bilan(s) > {jours} j")


def _sauvegarde_auto(con) -> None:
    """Sauvegarde chiffrée automatique au déverrouillage (si due). Ne doit
    jamais empêcher le déverrouillage : best-effort."""
    from . import sauvegarde  # import tardif (évite un cycle au chargement)

    try:
        cfg = config.ConfigStore(con).effective()
        res = sauvegarde.auto_si_due(con, cfg)
        if res:
            audit("sauvegarde_auto", "app", None, f"{res['octets']} octets")
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
