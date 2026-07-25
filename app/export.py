"""Export d'un bilan : Markdown, texte, et Word (.docx) — pour un CR éditable."""
from __future__ import annotations

import io

from .patient import age_texte, date_fr

DISCLAIMER = (
    "Document généré comme aide à la rédaction, relu et validé par l'orthophoniste : "
    "la responsabilité du contenu lui revient entièrement. "
    "L'outil ne pose aucun diagnostic."
)

_TYPE_LBL = {
    "initial_simple": "Bilan initial (simple)",
    "initial_complexe": "Bilan initial (complexe)",
    "renouvellement": "Bilan de renouvellement",
}


def _naissance(p: dict) -> str:
    """Mention de naissance accordée au sexe *enregistré*, sans parenthèse.

    Le sexe est une donnée du dossier : quand il est connu, l'accorder est plus
    juste qu'un « né(e) » parenthésé dans un document adressé au prescripteur.
    Quand il ne l'est pas (non renseigné, ou « autre »), la date est introduite
    sans participe plutôt que par une forme genrée par défaut."""
    date = date_fr(p["date_naissance"])
    participe = {"F": "née", "M": "né"}.get((p.get("sexe") or "").strip().upper())
    return f"{participe} le {date}" if participe else f"date de naissance : {date}"


def _patient_ligne(b: dict) -> str:
    p = b.get("patient")
    if not p:
        return ""
    ident = " ".join(x for x in [(p.get("nom") or "").upper(), p.get("prenom") or ""] if x)
    ligne = f"Patient : {ident or '—'}"
    if p.get("date_naissance"):
        ligne += f", {_naissance(p)}"
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
