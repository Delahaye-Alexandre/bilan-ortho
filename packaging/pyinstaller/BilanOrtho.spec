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
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# Bibliothèques à extensions natives : DLL embarquées explicitement
# (problèmes de chargement connus PyInstaller + Windows).
binaries = collect_dynamic_libs("sqlcipher3") + collect_dynamic_libs("ctranslate2")

# sqlite-vec charge son extension depuis le dossier du paquet.
vec_datas, vec_binaries, vec_hidden = collect_all("sqlite_vec")
binaries += vec_binaries

# reportlab (export PDF) embarque ses métriques de polices Type 1 comme données
# de paquet : sans elles, l'export PDF planterait dans l'app compilée alors
# qu'il fonctionne en développement — exactement la classe de bug qui a cassé
# la dictée entre la v1.2 et la v1.4 (assets faster-whisper manquants).
rl_datas, rl_binaries, rl_hidden = collect_all("reportlab")
binaries += rl_binaries

datas = [
    ("../../app/static", "app/static"),
    ("../../data/reference", "data/reference"),
] + vec_datas + rl_datas + collect_data_files("faster_whisper")  # assets/ : VAD Silero (onnx)

hiddenimports = (
    ["sqlcipher3", "app.main", "faster_whisper"]
    + vec_hidden
    + rl_hidden
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
