"""Import des bilans du praticien : extraction texte (PDF natif / OCR,
.docx/.odt, texte), découpage par rubrique, puis ingestion dans le RAG
(rag.add_reference). Sert aussi à reprendre la trame d'un bilan (lot C du
plan « mise en forme ») : les intitulés du document, dans l'ordre, deviennent
une proposition de trame que le praticien vérifie avant d'enregistrer.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
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


@dataclass
class Ligne:
    """Une ligne du document extrait, avec ce que son format sait d'elle.

    `niveau` : niveau de titre stylé (1 = « Titre 1 », 2 = « Titre 2 »…,
    0 = style « Titre » du document), None pour du texte courant. `gras` :
    paragraphe Word entièrement en gras sans style de titre — la façon la plus
    répandue d'écrire un intertitre."""

    texte: str
    niveau: int | None = None
    gras: bool = False


def cle_de_rubrique(titre: str) -> str:
    """Clé de rubrique déduite d'un intitulé : minuscules sans accent, mots
    séparés par « _ » (« Contexte scolaire » → « contexte_scolaire »). Même
    règle côté trame proposée et côté recherche d'extraits (rag.retrieve) :
    une rubrique reprise d'un bilan retrouve les extraits de ce bilan."""
    plat = unicodedata.normalize("NFKD", titre or "").encode("ascii", "ignore").decode()
    cle = re.sub(r"[^a-z0-9]+", "_", plat.lower()).strip("_")
    return cle[:40].strip("_") or "rubrique"


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


_NIVEAU_STYLE = re.compile(r"^(?:heading|titre)\s*(\d+)", re.I)


def _niveau_style(nom_style: str) -> int | None:
    """Niveau de titre d'un style Word (« Heading 1 », « Titre 2 », « Title »),
    None pour un style ordinaire (« Normal », « Sous-titre », « List Bullet »)."""
    nom = (nom_style or "").strip().lower()
    if nom in ("title", "titre"):
        return 0
    m = _NIVEAU_STYLE.match(nom)
    if m:
        return int(m.group(1))
    if nom.startswith("heading"):
        return 1
    return None


def _docx_lignes(data: bytes) -> list[Ligne]:
    """Lignes d'un .docx, mise en forme conservée en Markdown restreint.

    Le gras, l'italique, le souligné et les listes des bilans du praticien
    font partie de son style : conservés dans les extraits de référence, ils
    montrent au modèle ce que ce praticien met en relief. Les titres stylés
    restent en clair, seuls sur leur ligne, avec leur niveau ; un paragraphe
    entièrement en gras est signalé (intertitre probable). Les tableaux du
    document ne sont pas lus (limite connue)."""
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:
        raise ValueError("Fichier .docx illisible (corrompu ?).") from exc
    lignes: list[Ligne] = []
    for p in doc.paragraphs:
        niveau = _niveau_style(p.style.name if p.style is not None else "")
        if niveau is not None:
            lignes.append(Ligne(p.text, niveau))
            continue
        segments = [
            texte_riche.Segment(r.text, bool(r.bold), bool(r.italic), bool(r.underline))
            for r in p.runs if r.text
        ]
        ligne = texte_riche.serialiser_segments(segments)
        liste = _docx_format_liste(doc, p)
        if liste is not None and ligne.strip():
            ligne = ("1. " if liste else "- ") + ligne.strip()
        pleins = [r for r in p.runs if r.text.strip()]
        gras = liste is None and bool(pleins) and all(bool(r.bold) for r in pleins)
        lignes.append(Ligne(ligne, None, gras))
    return lignes


def _docx_text(data: bytes) -> str:
    return "\n".join(ligne.texte for ligne in _docx_lignes(data))


def _odt_lignes(data: bytes) -> list[Ligne]:
    """Lignes d'un .odt (LibreOffice/OpenOffice) : zip contenant content.xml.
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
    # Un paragraphe (text:p) ou un titre (text:h, avec son niveau de plan) =
    # une ligne : les en-têtes restent seuls sur leur ligne, condition pour que
    # le découpage les repère.
    lignes: list[Ligne] = []
    for el in racine.iter():
        if el.tag == ns + "h":
            try:
                niveau = int(el.get(ns + "outline-level", "1"))
            except ValueError:
                niveau = 1
            lignes.append(Ligne("".join(el.itertext()), niveau))
        elif el.tag == ns + "p":
            lignes.append(Ligne("".join(el.itertext())))
    return lignes


def _odt_text(data: bytes) -> str:
    return "\n".join(ligne.texte for ligne in _odt_lignes(data))


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


def extraire_lignes(data: bytes, filename: str) -> list[Ligne]:
    """Lignes du document avec leur nature (titre stylé, gras) quand le format
    la connaît (.docx, .odt) ; texte nu sinon. Lève ValueError si aucun texte
    n'en sort (PDF scanné sans OCR, format inconnu, fichier corrompu)."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".docx":
        lignes = _docx_lignes(data)
    elif ext == ".odt":
        lignes = _odt_lignes(data)
    else:
        lignes = [Ligne(ligne) for ligne in extract_text(data, filename).splitlines()]
    if not any(ligne.texte.strip() for ligne in lignes):
        if sys.platform == "win32":
            aide = ("Installez Tesseract pour Windows (installeur UB-Mannheim : "
                    "github.com/UB-Mannheim/tesseract) puis relancez l'import.")
        else:
            aide = ("Installez Tesseract "
                    "(apt install tesseract-ocr tesseract-ocr-fra ocrmypdf).")
        raise ValueError(f"Aucun texte extrait. PDF scanné ? {aide}")
    return lignes


def _en_clair(ligne: str) -> str:
    """Un praticien met souvent ses intertitres en gras : l'en-tête est repéré
    sur la version en clair, et le titre retenu est en clair."""
    s = ligne.strip()
    return texte_riche.en_clair(s) if "*" in s or "<u>" in s else s


# Numérotation en tête d'un intitulé (« 1. », « II - », « a) ») : retirée du
# titre repris, la trame numérote elle-même si le praticien le demande.
_NUMEROTATION = re.compile(r"^\s*(?:\d{1,2}\s*[.)\-–]|[IVX]{1,4}\s*[.)\-–]|[A-Za-z][.)])\s+")


def _titre_propre(ligne: str) -> str:
    t = _NUMEROTATION.sub("", _en_clair(ligne)).strip().rstrip(":").strip()
    return re.sub(r"\s+", " ", t)[:80]


def decouper_lignes(lignes: list[Ligne]) -> list[tuple[str, str, str]]:
    """Découpe des lignes en extraits (clé de rubrique, titre, contenu).

    Un en-tête est un titre stylé (Word, LibreOffice) ou une ligne courte qui
    commence par un mot-clé du tronc commun. La clé est celle du mot-clé ;
    un titre stylé sans mot-clé (« Contexte scolaire ») ouvre son propre
    extrait mais garde la clé de la rubrique en cours : il reste retrouvable
    pour cette rubrique, et par son intitulé si le praticien reprend la trame
    du document (rag.retrieve). Le texte avant le premier en-tête est
    « global » (bloc d'identité, écarté à l'import)."""
    cur_cle, cur_titre, buf = "global", "Extrait", []
    out: list[tuple[str, str, str]] = []

    def flush():
        contenu = "\n".join(buf).strip()
        if contenu:
            out.append((cur_cle, cur_titre, contenu))

    for ligne in lignes:
        s = _en_clair(ligne.texte)
        cle = _is_heading(s)
        if cle or (ligne.niveau is not None and ligne.niveau >= 1 and s):
            flush()
            cur_cle, cur_titre, buf = cle or cur_cle, _titre_propre(ligne.texte), []
        else:
            buf.append(ligne.texte)
    flush()
    # Si rien n'a été segmenté, tout le texte devient un extrait « global ».
    texte = "\n".join(ligne.texte for ligne in lignes).strip()
    return [c for c in out if c[2].strip()] or [("global", "Extrait", texte)]


def sectionize(text: str) -> list[tuple[str, str, str]]:
    """Découpe un texte nu en (clé de rubrique, titre, texte) via des en-têtes
    (mots-clés du tronc commun)."""
    return decouper_lignes([Ligne(ligne) for ligne in text.splitlines()])


def decouper(data: bytes, filename: str) -> list[tuple[str, str, str]]:
    """Extrait le texte puis le découpe en extraits (clé, titre, contenu).

    Fonction pure (CPU/OCR, aucun réseau ni base) : l'appelant calcule les
    embeddings hors verrou puis insère via ``rag.add_reference``."""
    return decouper_lignes(extraire_lignes(data, filename))


# --- Reprendre la trame d'un bilan (lot C) -------------------------------------

# Titre du document lui-même, pas une rubrique (sauf s'il porte un mot-clé).
_TITRE_DOCUMENT = re.compile(
    r"^(compte[\s-]*rendu|bilan orthophonique|bilan de |rapport)", re.I
)
_CHIFFRE_OU_SCORE = re.compile(r"\d")


def _titre_probable(texte: str, suivante: str) -> bool:
    """Ligne courte isolée qui ressemble à un intertitre, dans un document sans
    styles ni gras (PDF, texte) : sept mots au plus, majuscule initiale, sans
    ponctuation finale ni chiffre, suivie d'un vrai paragraphe ou d'une liste."""
    s = texte.strip()
    if s.startswith(("-", "•", "–", "*")):
        return False
    t = _NUMEROTATION.sub("", s).rstrip(":").strip()
    if not (3 <= len(t) <= 60) or t[-1] in ".,;!?" or not t[0].isupper():
        return False
    if not 1 <= len(t.split()) <= 7 or _CHIFFRE_OU_SCORE.search(t):
        return False
    apres = suivante.strip()
    return len(apres) >= 40 or apres.startswith(("-", "•", "1.", "–"))


def proposer_trame_lignes(lignes: list[Ligne]) -> dict | None:
    """Trame proposée d'après les intitulés du document, dans l'ordre.

    Toujours les mots-clés du tronc commun, plus le signal le plus sûr que le
    document offre : titres stylés (au niveau de plan qui en compte au moins
    deux), sinon paragraphes Word entièrement en gras, sinon lignes courtes
    isolées.
    Retourne {"sections": [{"cle", "titre"}], "detection": …} ou None si
    moins de deux rubriques se dégagent. Rien n'est enregistré : le praticien
    relit la proposition dans l'éditeur de trame."""
    styles: dict[int, list[int]] = {}
    for i, ligne in enumerate(lignes):
        if ligne.niveau is not None and ligne.niveau >= 1 and ligne.texte.strip():
            styles.setdefault(ligne.niveau, []).append(i)
    niveau_retenu = next((n for n in sorted(styles) if len(styles[n]) >= 2), None)
    indices_styles = set(styles.get(niveau_retenu, []))

    def candidats(origines: set[str]) -> list[tuple[str, str | None]]:
        vus: set[str] = set()
        out: list[tuple[str, str | None]] = []
        for i, ligne in enumerate(lignes):
            s = _en_clair(ligne.texte)
            if not s:
                continue
            mot_cle = _is_heading(s)
            suivante = lignes[i + 1].texte if i + 1 < len(lignes) else ""
            retenu = bool(mot_cle) or (
                ("styles" in origines and i in indices_styles)
                or ("gras" in origines and ligne.gras and ligne.niveau is None
                    and _titre_probable(s, suivante))
                or ("lignes" in origines and ligne.niveau is None and not ligne.gras
                    and _titre_probable(s, suivante))
            )
            if not retenu:
                continue
            titre = _titre_propre(ligne.texte)
            if not titre or (not mot_cle and _TITRE_DOCUMENT.match(titre)):
                continue
            slug = cle_de_rubrique(titre)
            if slug in vus:
                continue
            vus.add(slug)
            out.append((titre, mot_cle))
        return out

    # Le signal le plus sûr que le document offre décide, pour ses intitulés
    # sans mot-clé : des titres stylés font ignorer le gras et les lignes
    # courtes (moins de faux intertitres) ; du gras fait ignorer les lignes
    # courtes ; un texte nu n'a que les lignes courtes.
    if niveau_retenu is not None:
        detection = "styles"
    elif any(ligne.gras and ligne.niveau is None for ligne in lignes):
        detection = "gras"
    else:
        detection = "lignes"
    retenus = candidats({detection})
    if len(retenus) < 2 or len(retenus) > 25:
        # Rien de net, ou plus de vingt-cinq « rubriques » (des lignes de contenu).
        return None
    sections: list[dict] = []
    cles: set[str] = set()
    for titre, mot_cle in retenus:
        cle = mot_cle if mot_cle and mot_cle not in cles else cle_de_rubrique(titre)
        base, n = cle, 2
        while cle in cles:
            cle, n = f"{base}_{n}", n + 1
        cles.add(cle)
        sections.append({"cle": cle, "titre": titre})
    return {"sections": sections, "detection": detection}


def proposer_trame(data: bytes, filename: str) -> dict | None:
    return proposer_trame_lignes(extraire_lignes(data, filename))


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
