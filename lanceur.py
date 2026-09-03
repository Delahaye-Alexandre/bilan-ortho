"""Point d'entrée natif de Bilan Ortho (compilé par PyInstaller sous Windows).

Double-clic : si une instance répond déjà sur un port local, ouvre simplement
le navigateur dessus (single-instance) ; sinon démarre le serveur sur le
premier port libre et ouvre le navigateur dès qu'il répond. En mode compilé
(fenêtré, sans console), les journaux partent dans <données>/serveur.log.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import httpx

PORTS = range(8000, 8011)

# Navigateurs chromium capables du mode « application » (fenêtre dédiée sans
# barre d'adresse ni onglets — l'app ressemble à un vrai logiciel).
_NAVIGATEURS_APP = [
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
]


def _ouvrir_fenetre(url: str) -> None:
    """Ouvre l'app dans une fenêtre dédiée (mode --app) ; à défaut, navigateur."""
    if sys.platform == "win32":
        for gabarit in _NAVIGATEURS_APP:
            exe = os.path.expandvars(gabarit)
            if os.path.exists(exe):
                subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860"])
                return
    webbrowser.open(url)


def _instance_existante() -> str | None:
    """URL d'une instance Bilan Ortho déjà en cours, sinon None."""
    for p in PORTS:
        try:
            r = httpx.get(f"http://127.0.0.1:{p}/api/status", timeout=0.5)
            if r.status_code == 200 and "db_exists" in r.json():
                return f"http://127.0.0.1:{p}"
        except Exception:
            continue
    return None


def _port_libre() -> int:
    for p in PORTS:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit("Aucun port local libre (8000-8010).")


def _attendre_pret(url: str, essais: int = 240) -> bool:
    """Sonde /api/status jusqu'à 2 minutes (premier démarrage plus lent).
    True dès que le serveur répond, False s'il n'a jamais répondu."""
    for _ in range(essais):
        try:
            if httpx.get(f"{url}/api/status", timeout=0.5).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _boite_erreur(message: str) -> None:
    """Boîte de dialogue d'erreur native (l'app est fenêtrée, sans console)."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Bilan Ortho", 0x10)
    else:
        print(message, file=sys.stderr)


def _ouvrir_quand_pret(url: str) -> None:
    """N'ouvre le navigateur QUE si le serveur a fini par répondre : ouvrir une
    page d'erreur brute n'aiderait pas — on indique plutôt où est le journal."""
    if _attendre_pret(url):
        _ouvrir_fenetre(url)
        return
    from app import config

    _boite_erreur(
        "Bilan Ortho n'a pas démarré (le serveur ne répond pas après 2 minutes).\n"
        f"Détails dans le journal : {config.data_dir() / 'serveur.log'}"
    )


def _port_demande(argv: list[str]) -> int | None:
    """Port passé par l'installeur après une mise à jour (--port=N)."""
    for arg in argv:
        if arg.startswith("--port="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                return None
    return None


def _attendre_port(port: int, essais: int = 40) -> bool:
    """Le port de l'instance qui vient d'être fermée peut rester occupé
    quelques secondes (connexions en cours de clôture) : on patiente."""
    for _ in range(essais):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                time.sleep(0.5)
    return False


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    url = _instance_existante()
    if url:
        _ouvrir_fenetre(url)
        return

    # Relance par l'installeur après une mise à jour en un clic : on reprend
    # le port de l'instance remplacée pour que la page restée ouverte se
    # reconnecte d'elle-même, sans ouvrir une seconde fenêtre. Si le port ne
    # se libère pas, retour au comportement normal (port libre + fenêtre).
    port_voulu = _port_demande(argv)
    if port_voulu and port_voulu in PORTS and _attendre_port(port_voulu):
        port = port_voulu
        ouvrir_fenetre = "--sans-fenetre" not in argv
    else:
        port = _port_libre()
        ouvrir_fenetre = True
    if ouvrir_fenetre:
        threading.Thread(
            target=_ouvrir_quand_pret, args=(f"http://127.0.0.1:{port}",), daemon=True
        ).start()

    if getattr(sys, "frozen", False):
        # Mode fenêtré : pas de console -> journal dans le dossier de données.
        from app import config

        chemin = config.data_dir() / "serveur.log"
        # Rotation simple : au-delà de 5 Mo, l'ancien journal devient
        # serveur.log.1 (écrasé) — le fichier ne grossit plus à l'infini.
        try:
            if chemin.exists() and chemin.stat().st_size > 5 * 1024 * 1024:
                chemin.replace(chemin.with_suffix(".log.1"))
        except OSError:
            pass
        log = open(chemin, "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log

    import uvicorn

    from app.main import app  # import direct : compatible PyInstaller

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    # Indispensable en app compilée (PyInstaller/Windows) : les bibliothèques
    # qui créent des processus (ocrmypdf…) relanceraient l'app en boucle sinon.
    import multiprocessing

    multiprocessing.freeze_support()
    main()
