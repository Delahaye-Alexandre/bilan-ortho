"""Import des bilans du praticien : extraction texte (PDF natif / OCR / texte),
découpage par rubrique, puis ingestion dans le RAG (rag.add_reference).
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

from . import rag

# Mots-clés d'en-tête -> clé de rubrique (tronc commun).
_HEADINGS: list[tuple[str, str]] = [
    ("administratif", r"donn[ée]es administratives|identit[ée]|objet du bilan"),
    ("anamnese", r"anamn[èe]se|ant[ée]c[ée]dents|histoire|d[ée]veloppement"),
    ("observations", r"observ|comportement|attitude"),
    ("epreuves", r"[ée]preuves|tests|r[ée]sultats|passation|bilan (analytique|proprement)"),
    ("analyse", r"analyse|synth[èe]se|interpr[ée]tation"),
    ("diagnostic", r"diagnostic|conclusion"),
    ("projet", r"projet|r[ée][ée]ducation|prise en charge|propositions|objectifs"),
]
_HEADING_RE = [(cle, re.compile(pat, re.I)) for cle, pat in _HEADINGS]


def _ocr_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import ocrmypdf  # noqa: F401
        return True
    except ImportError:
        return False


def _ocr_pdf(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fi, \
         tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fo:
        fi.write(data)
        fi.flush()
        try:
            # Via l'interpréteur courant (-m) : ne dépend pas du PATH, cohérent
            # avec le `import ocrmypdf` vérifié par _ocr_available().
            subprocess.run(
                [sys.executable, "-m", "ocrmypdf",
                 "-l", "fra", "--force-ocr", "--quiet", fi.name, fo.name],
                check=True, capture_output=True,
            )
            return _pdf_text(open(fo.name, "rb").read())
        finally:
            for p in (fi.name, fo.name):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def extract_text(data: bytes, filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".pdf":
        text = _pdf_text(data)
        if len(text.strip()) < 20 and _ocr_available():
            text = _ocr_pdf(data)  # PDF scanné
        return text
    # texte brut / markdown / autres
    return data.decode("utf-8", errors="ignore")


def _is_heading(s: str) -> str | None:
    """Une ligne est un en-tête si : courte, sans ponctuation finale, et le
    mot-clé de rubrique apparaît en tout début (évite les phrases de contenu)."""
    if not (0 < len(s) <= 45) or s[-1] in ".,;:":
        return None
    for cle, rx in _HEADING_RE:
        m = rx.search(s.lower())
        if m and m.start() <= 3:
            return cle
    return None


def sectionize(text: str) -> list[tuple[str, str, str]]:
    """Découpe le texte en (clé de rubrique, titre, texte) via des en-têtes."""
    cur_cle, cur_titre, buf = "global", "Extrait", []
    out: list[tuple[str, str, str]] = []

    def flush():
        contenu = "\n".join(buf).strip()
        if contenu:
            out.append((cur_cle, cur_titre, contenu))

    for line in text.splitlines():
        s = line.strip()
        cle = _is_heading(s)
        if cle:
            flush()
            cur_cle, cur_titre, buf = cle, s, []
        else:
            buf.append(line)
    flush()
    # Si rien n'a été segmenté, tout le texte devient un extrait « global ».
    return out or [("global", "Extrait", text.strip())]


def import_bilan(
    con, data: bytes, filename: str, domaine: str, cfg: dict,
    praticien_id=None, source: str = "import",
) -> dict:
    text = extract_text(data, filename)
    if not text.strip():
        raise ValueError(
            "Aucun texte extrait. PDF scanné ? Installez Tesseract "
            "(apt install tesseract-ocr tesseract-ocr-fra ocrmypdf)."
        )
    chunks = sectionize(text)
    ids = []
    for cle, titre, contenu in chunks:
        if contenu.strip():
            ids.append(
                rag.add_reference(con, praticien_id, source, domaine, cle, titre, contenu, cfg)
            )
    return {"n": len(ids), "sections": [c[0] for c in chunks], "filename": filename}
