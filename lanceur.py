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


def _ouvrir_quand_pret(url: str) -> None:
    for _ in range(240):  # jusqu'à 2 minutes (premier démarrage plus lent)
        try:
            if httpx.get(f"{url}/api/status", timeout=0.5).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    _ouvrir_fenetre(url)


def main() -> None:
    url = _instance_existante()
    if url:
        _ouvrir_fenetre(url)
        return

    port = _port_libre()
    threading.Thread(
        target=_ouvrir_quand_pret, args=(f"http://127.0.0.1:{port}",), daemon=True
    ).start()

    if getattr(sys, "frozen", False):
        # Mode fenêtré : pas de console -> journal dans le dossier de données.
        from app import config

        log = open(config.data_dir() / "serveur.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log

    from app.main import app  # import direct : compatible PyInstaller

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    # Indispensable en app compilée (PyInstaller/Windows) : les bibliothèques
    # qui créent des processus (ocrmypdf…) relanceraient l'app en boucle sinon.
    import multiprocessing

    multiprocessing.freeze_support()
    main()
