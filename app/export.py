"""Export d'un bilan : Markdown, texte, et Word (.docx) — pour un CR éditable."""
from __future__ import annotations

import io

from .patient import age_texte, date_fr

DISCLAIMER = (
    "Document généré comme aide à la rédaction, relu et validé par l'orthophoniste, "
    "seul responsable du contenu. L'outil ne pose aucun diagnostic."
)

_TYPE_LBL = {
    "initial_simple": "Bilan initial (simple)",
    "initial_complexe": "Bilan initial (complexe)",
    "renouvellement": "Bilan de renouvellement",
}


def _patient_ligne(b: dict) -> str:
    p = b.get("patient")
    if not p:
        return ""
    ident = " ".join(x for x in [(p.get("nom") or "").upper(), p.get("prenom") or ""] if x)
    ligne = f"Patient : {ident or '—'}"
    if p.get("date_naissance"):
        ligne += f", né(e) le {date_fr(p['date_naissance'])}"
        age = age_texte(p["date_naissance"], b.get("created_at"))
        if age:
            ligne += f" ({age} à la date du bilan)"
    return ligne


def _content(b: dict) -> list[tuple[str, str]]:
    doms = b.get("domaine_titres") or "Générique"
    meta = f"{_TYPE_LBL.get(b.get('type'), b.get('type', ''))} · Domaine(s) : {doms}"
    blocks: list[tuple[str, str]] = [("h1", "Compte-rendu de bilan orthophonique"), ("p", meta)]
    patient = _patient_ligne(b)
    if patient:
        blocks.append(("p", patient))
    for s in b.get("sections", []):
        if (s.get("contenu") or "").strip():
            blocks.append(("h2", s["titre"]))
            blocks.append(("p", s["contenu"].strip()))
    cot = b.get("cotation")
    if cot:
        blocks.append(("h2", "Cotation (NGAP)"))
        blocks.append((
            "p",
            f"{cot['code_amo']} — {cot['montant']} € "
            f"(coefficient {cot['coefficient']}, valeur lettre-clé {cot['valeur_lettre_cle']} €)",
        ))
    blocks.append(("hr", ""))
    blocks.append(("i", DISCLAIMER))
    return blocks


def to_markdown(b: dict) -> str:
    out = []
    for k, t in _content(b):
        if k == "h1":
            out.append(f"# {t}")
        elif k == "h2":
            out.append(f"\n## {t}")
        elif k == "p":
            out.append(f"\n{t}")
        elif k == "hr":
            out.append("\n---")
        elif k == "i":
            out.append(f"\n_{t}_")
    return "\n".join(out).strip() + "\n"


def to_txt(b: dict) -> str:
    out = []
    for k, t in _content(b):
        if k in ("h1", "h2"):
            out.append("\n" + t.upper())
        elif k == "p":
            out.append(t)
        elif k == "hr":
            out.append("-" * 40)
        elif k == "i":
            out.append(t)
    return "\n".join(out).strip() + "\n"


def to_docx(b: dict) -> bytes:
    from docx import Document

    doc = Document()
    for k, t in _content(b):
        if k == "h1":
            doc.add_heading(t, level=0)
        elif k == "h2":
            doc.add_heading(t, level=1)
        elif k == "p":
            doc.add_paragraph(t)
        elif k == "hr":
            doc.add_paragraph("_" * 30)
        elif k == "i":
            p = doc.add_paragraph()
            p.add_run(t).italic = True
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
