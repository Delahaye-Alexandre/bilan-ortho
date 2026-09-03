"""Import des bilans du praticien : extraction texte (PDF natif / OCR,
.docx/.odt, texte), découpage par rubrique, puis ingestion dans le RAG
(rag.add_reference).
"""
from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from . import texte_riche

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


# Chemins d'installation standards de Tesseract sous Windows (installeur
# UB-Mannheim), cherchés quand le binaire n'est pas sur le PATH.
_TESSERACT_WIN = [
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
]


def _tesseract_dir() -> str | None:
    """Dossier contenant tesseract, ou None. Cherche PATH puis emplacements
    Windows standards."""
    exe = shutil.which("tesseract")
    if exe:
        return os.path.dirname(exe)
    if sys.platform == "win32":
        for d in _TESSERACT_WIN:
            if os.path.exists(os.path.join(d, "tesseract.exe")):
                return d
    return None


def _ocr_available() -> bool:
    if _tesseract_dir() is None:
        return False
    try:
        import ocrmypdf  # noqa: F401
        return True
    except ImportError:
        return False


def _ocr_pdf(data: bytes) -> str:
    # API Python d'ocrmypdf (pas de sous-processus Python : indispensable dans
    # l'application compilée PyInstaller, où `python -m` n'existe pas).
    # Tesseract/Ghostscript restent des binaires externes trouvés via le PATH :
    # on y ajoute l'emplacement Windows standard de Tesseract si besoin.
    import ocrmypdf

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fi, \
         tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fo:
        fi.write(data)
        fi.flush()
        ancien_path = os.environ.get("PATH", "")
        tess = _tesseract_dir()
        try:
            if tess and tess not in ancien_path:
                os.environ["PATH"] = tess + os.pathsep + ancien_path
            ocrmypdf.ocr(
                fi.name, fo.name,
                language="fra", force_ocr=True, progress_bar=False,
            )
            return _pdf_text(open(fo.name, "rb").read())
        finally:
            os.environ["PATH"] = ancien_path
            for p in (fi.name, fo.name):
                try:
                    os.unlink(p)
                except OSError:
                    pass


_PDF_ILLISIBLE = (
    "PDF illisible ou protégé par mot de passe. Réexportez-le sans protection, "
    "ou importez le document en .docx, .odt ou .txt."
)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    # Les exceptions pypdf (PdfReadError, FileNotDecryptedError…) ne sont pas
    # des ValueError : sans traduction, elles remontent en 500 opaque au lieu
    # du 400 explicite de la route d'import.
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise ValueError(_PDF_ILLISIBLE) from exc


def _docx_format_liste(doc, paragraphe) -> bool | None:
    """None si le paragraphe n'est pas un élément de liste, sinon True pour
    une liste numérotée et False pour une liste à puces."""
    nom_style = ((paragraphe.style.name if paragraphe.style is not None else "") or "").lower()
    ppr = paragraphe._p.pPr
    num_pr = ppr.numPr if ppr is not None else None
    if num_pr is None and "list" not in nom_style and "liste" not in nom_style:
        return None
    # Le format réel (puce ou décimal) vit dans les définitions de numérotation ;
    # à défaut, le nom du style tranche (« List Number », « Liste à numéros »).
    try:
        from docx.oxml.ns import qn

        num_id = num_pr.numId.val if num_pr is not None else (
            paragraphe.style.element.pPr.numPr.numId.val
        )
        numbering = doc.part.numbering_part.element
        abstract_id = numbering.num_having_numId(num_id).abstractNumId.val
        for abstrait in numbering.findall(qn("w:abstractNum")):
            if abstrait.get(qn("w:abstractNumId")) == str(abstract_id):
                fmt = abstrait.find(f"{qn('w:lvl')}[@{qn('w:ilvl')}='0']/{qn('w:numFmt')}")
                if fmt is not None:
                    return fmt.get(qn("w:val")) != "bullet"
    except Exception:
        pass
    return "number" in nom_style or "numéro" in nom_style


def _docx_text(data: bytes) -> str:
    """Texte d'un .docx, mise en forme conservée en Markdown restreint.

    Le gras, l'italique, le souligné et les listes des bilans du praticien
    font partie de son style : conservés dans les extraits de référence, ils
    montrent au modèle ce que ce praticien met en relief. Les titres restent
    en clair, seuls sur leur ligne, condition pour que sectionize() les repère.
    Les tableaux du document ne sont pas lus (limite connue)."""
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:
        raise ValueError("Fichier .docx illisible (corrompu ?).") from exc
    lignes: list[str] = []
    for p in doc.paragraphs:
        nom_style = ((p.style.name if p.style is not None else "") or "").lower()
        if nom_style.startswith(("heading", "titre", "title")):
            lignes.append(p.text)
            continue
        segments = [
            texte_riche.Segment(r.text, bool(r.bold), bool(r.italic), bool(r.underline))
            for r in p.runs if r.text
        ]
        ligne = texte_riche.serialiser_segments(segments)
        liste = _docx_format_liste(doc, p)
        if liste is not None and ligne.strip():
            ligne = ("1. " if liste else "- ") + ligne.strip()
        lignes.append(ligne)
    return "\n".join(lignes)


def _odt_text(data: bytes) -> str:
    """Texte d'un .odt (LibreOffice/OpenOffice) : zip contenant content.xml.
    Extraction en stdlib (zipfile + ElementTree) — pas de dépendance dédiée."""
    ns = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            racine = ET.fromstring(z.read("content.xml"))
    except Exception as exc:
        raise ValueError("Fichier .odt illisible (corrompu ?).") from exc
    # L'ODF encode tabulations, espaces multiples et sauts de ligne en éléments
    # vides, invisibles pour itertext() : sans traduction, « EVALO⇥-2,1 »
    # ressortirait collé (« EVALO-2,1 ») dans les extraits de style.
    for el in racine.iter():
        if el.tag in (ns + "s", ns + "tab"):
            el.text = " "
        elif el.tag == ns + "line-break":
            el.text = "\n"
    # Un paragraphe (text:p) ou un titre (text:h) = une ligne : les en-têtes
    # restent seuls sur leur ligne, condition pour que sectionize() les repère.
    return "\n".join(
        "".join(el.itertext())
        for el in racine.iter()
        if el.tag in (ns + "p", ns + "h")
    )


_FORMATS_ACCEPTES = ".pdf, .docx, .odt, .txt, .md"


def extract_text(data: bytes, filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".pdf":
        text = _pdf_text(data)
        if len(text.strip()) < 20 and _ocr_available():
            try:
                text = _ocr_pdf(data)  # PDF scanné
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(_PDF_ILLISIBLE) from exc
        return text
    if ext == ".docx":
        return _docx_text(data)
    if ext == ".odt":
        return _odt_text(data)
    if ext in ("", ".txt", ".md", ".markdown"):
        # Un binaire décodé en errors="ignore" polluait la base RAG : rejet.
        if b"\x00" in data:
            raise ValueError(
                f"Fichier binaire non pris en charge. Formats acceptés : {_FORMATS_ACCEPTES}."
            )
        return data.decode("utf-8", errors="ignore")
    raise ValueError(
        f"Format « {ext} » non pris en charge. Formats acceptés : {_FORMATS_ACCEPTES}."
    )


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
        # Un praticien met souvent ses intertitres en gras : l'en-tête est
        # repéré sur la version en clair, et le titre retenu est en clair.
        s = texte_riche.en_clair(line.strip()) if "*" in line or "<u>" in line else line.strip()
        cle = _is_heading(s)
        if cle:
            flush()
            cur_cle, cur_titre, buf = cle, s, []
        else:
            buf.append(line)
    flush()
    # Si rien n'a été segmenté, tout le texte devient un extrait « global ».
    return out or [("global", "Extrait", text.strip())]


def decouper(data: bytes, filename: str) -> list[tuple[str, str, str]]:
    """Extrait le texte puis le découpe en extraits (clé, titre, contenu).

    Fonction pure (CPU/OCR, aucun réseau ni base) : l'appelant calcule les
    embeddings hors verrou puis insère via ``rag.add_reference``."""
    text = extract_text(data, filename)
    if not text.strip():
        if sys.platform == "win32":
            aide = ("Installez Tesseract pour Windows (installeur UB-Mannheim : "
                    "github.com/UB-Mannheim/tesseract) puis relancez l'import.")
        else:
            aide = ("Installez Tesseract "
                    "(apt install tesseract-ocr tesseract-ocr-fra ocrmypdf).")
        raise ValueError(f"Aucun texte extrait. PDF scanné ? {aide}")
    return [c for c in sectionize(text) if c[2].strip()]


# --- Pack de démarrage (bilans fictifs embarqués) ----------------------------

# Résolu depuis app/ : vaut aussi bien en dev qu'en application gelée, où le
# spec PyInstaller embarque data/reference au même chemin relatif.
PACK_DIR = Path(__file__).parent.parent / "data" / "reference"


def pack_fichiers() -> list[tuple[str, str, bytes]]:
    """Fichiers du pack embarqué : (nom, clé de domaine, contenu).

    La clé de domaine se déduit du nom — ``bilan-fictif-<domaine>.txt``,
    tirets → underscores (convention documentée dans data/reference/README.md)."""
    out = []
    for p in sorted(PACK_DIR.glob("*.txt")):
        domaine = p.stem.removeprefix("bilan-fictif-").replace("-", "_")
        out.append((p.name, domaine, p.read_bytes()))
    return out
