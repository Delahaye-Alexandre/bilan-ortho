# Spec PyInstaller — application Windows native Bilan Ortho (mode onedir).
#
# Build (depuis la racine du projet) :
#   python packaging/windows/genere_icone.py packaging/windows/icone.ico
#   pyinstaller packaging/pyinstaller/BilanOrtho.spec --noconfirm
# Produit : dist/BilanOrtho/BilanOrtho.exe (+ _internal/)
#
# Choix : onedir (démarrage rapide, moins de faux positifs antivirus),
# fenêtré (les journaux vont dans <données>/serveur.log via lanceur.py).

from PyInstaller.utils.hooks import (
    collect_all,
    collect_dynamic_libs,
    collect_submodules,
)

# Bibliothèques à extensions natives : DLL embarquées explicitement
# (problèmes de chargement connus PyInstaller + Windows).
binaries = collect_dynamic_libs("sqlcipher3") + collect_dynamic_libs("ctranslate2")

# sqlite-vec charge son extension depuis le dossier du paquet.
vec_datas, vec_binaries, vec_hidden = collect_all("sqlite_vec")
binaries += vec_binaries

datas = [
    ("../../app/static", "app/static"),
    ("../../data/reference", "data/reference"),
] + vec_datas

hiddenimports = (
    ["sqlcipher3", "app.main", "faster_whisper"]
    + vec_hidden
    + collect_submodules("uvicorn")   # boucles/protocoles chargés dynamiquement
)

a = Analysis(
    ["../../lanceur.py"],
    pathex=["../.."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="BilanOrtho",
    icon="../windows/icone.ico",
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="BilanOrtho",
)
