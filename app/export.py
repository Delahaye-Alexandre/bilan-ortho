"""Export d'un bilan : Markdown, texte, Word (.docx) et PDF.

Le compte-rendu de bilan orthophonique est un document adressé au médecin
prescripteur. Il portait jusqu'ici les seules rubriques : ni identité du
praticien, ni date, ni destinataire, ni signature — donc rien qui permette de
l'envoyer tel quel. Le praticien recollait le texte dans son papier à en-tête,
ce qui reprenait le temps que l'outil venait de faire gagner.

L'en-tête, le destinataire et la signature n'apparaissent que s'ils ont été
renseignés : aucune identité n'est inventée, et un coffre neuf produit le même
document qu'avant.
"""
from __future__ import annotations

import io

from . import cotation, texte_riche
from .bilan import DRAPEAU_LIBELLE, etalonnage_texte
from .patient import age_texte, date_fr

DISCLAIMER = (
    "Document généré comme aide à la rédaction, relu et validé par l'orthophoniste : "
    "la responsabilité du contenu lui revient entièrement. "
    "L'outil ne pose aucun diagnostic."
)

# Tant que le bilan n'est pas marqué validé, le document le dit lui-même : sans
# cette mention, l'export d'un brouillon non relu était indiscernable du
# compte-rendu définitif — exactement le geste qu'un outil médico-légal doit
# rendre difficile.
MENTION_BROUILLON = (
    "BROUILLON — document de travail non validé, à ne pas transmettre en l'état."
)

_TYPE_LBL = {
    "initial_simple": "Bilan initial (simple)",
    "initial_complexe": "Bilan initial (complexe)",
    "renouvellement": "Bilan de renouvellement",
}

_COLONNES = ["Test", "Épreuve", "Score brut", "Étalonnage", "Interprétation"]

# Titres déjà porteurs de civilité : n'en ajoutons pas une seconde.
_CIVILITES = ("dr", "dr.", "docteur", "pr", "pr.", "professeur", "mme", "m.", "mr")


def _naissance(p: dict) -> str:
    """Mention de naissance accordée au sexe *enregistré*, sans parenthèse.

    Le sexe est une donnée du dossier : quand il est connu, l'accorder est plus
    juste qu'un « né(e) » parenthésé dans un document adressé au prescripteur.
    Quand il ne l'est pas (non renseigné, ou « autre »), la date est introduite
    sans participe plutôt que par une forme genrée par défaut."""
    date = date_fr(p["date_naissance"])
    participe = {"F": "née", "M": "né"}.get((p.get("sexe") or "").strip().upper())
    return f"{participe} le {date}" if participe else f"date de naissance : {date}"


def _date_reference(b: dict) -> str:
    """Date du bilan, à défaut sa date de création.

    L'âge doit être calculé à la date du bilan : un compte-rendu rédigé une
    semaine plus tard ne doit pas vieillir le patient d'autant."""
    return (b.get("date_bilan") or "").strip() or (b.get("created_at") or "")


def _patient_ligne(b: dict) -> str:
    p = b.get("patient")
    if not p:
        return ""
    ident = " ".join(x for x in [(p.get("nom") or "").upper(), p.get("prenom") or ""] if x)
    ligne = f"Patient : {ident or '—'}"
    if p.get("date_naissance"):
        ligne += f", {_naissance(p)}"
        age = age_texte(p["date_naissance"], _date_reference(b))
        if age:
            ligne += f" ({age} à la date du bilan)"
    return ligne


def _nom_praticien(prat: dict) -> str:
    return " ".join(
        x for x in [(prat.get("prenom") or "").strip(), (prat.get("nom") or "").strip()] if x
    )


def _entete_praticien(prat: dict) -> list[str]:
    """Lignes d'en-tête du cabinet, dans l'ordre d'un papier à lettres.

    Sans nom, pas d'en-tête du tout : `titre` vaut « Orthophoniste » par défaut,
    et le seul métier ne constitue pas une identité — un coffre neuf produirait
    un en-tête qui n'identifie personne."""
    nom = _nom_praticien(prat)
    if not nom:
        return []
    lignes = [nom]
    if (prat.get("titre") or "").strip():
        lignes.append(prat["titre"].strip())
    ville = " ".join(
        x for x in [(prat.get("code_postal") or "").strip(), (prat.get("ville") or "").strip()] if x
    )
    adresse = ", ".join(x for x in [(prat.get("adresse") or "").strip(), ville] if x)
    if adresse:
        lignes.append(adresse)
    contact = " — ".join(
        x for x in [
            f"Tél. {prat['telephone'].strip()}" if (prat.get("telephone") or "").strip() else "",
            (prat.get("email") or "").strip(),
        ] if x
    )
    if contact:
        lignes.append(contact)
    ids = " — ".join(
        x for x in [
            f"N° ADELI {prat['adeli'].strip()}" if (prat.get("adeli") or "").strip() else "",
            f"RPPS {prat['rpps'].strip()}" if (prat.get("rpps") or "").strip() else "",
            f"SIRET {prat['siret'].strip()}" if (prat.get("siret") or "").strip() else "",
        ] if x
    )
    if ids:
        lignes.append(ids)
    return lignes


def _destinataire(b: dict) -> str:
    nom = ((b.get("prescripteur") or {}).get("nom") or "").strip()
    if not nom:
        return ""
    premier = nom.split()[0].lower()
    if premier in _CIVILITES:
        return f"À l'attention de {nom}"
    return f"À l'attention du Dr {nom}"


def _signature(b: dict, prat: dict) -> list[str]:
    """« Fait à …, le … » puis l'identité qui signe. Rien sans identité."""
    nom = _nom_praticien(prat)
    if not nom:
        return []
    lieu = (prat.get("lieu_signature") or "").strip() or (prat.get("ville") or "").strip()
    quand = date_fr(_date_reference(b)[:10]) if _date_reference(b) else ""
    formule = ", le ".join(x for x in [f"Fait à {lieu}" if lieu else "Fait", quand] if x)
    titre = (prat.get("titre") or "").strip()
    return [formule, f"{nom}, {titre.lower()}" if titre else nom]


def _table_epreuves(b: dict) -> list[list[str]] | None:
    """Lignes du tableau des résultats, ou None s'il n'y a rien à montrer."""
    lignes: list[list[str]] = []
    for e in b.get("epreuves") or []:
        for r in e.get("resultats") or []:
            interpretation = " ".join(
                x for x in [
                    DRAPEAU_LIBELLE.get(r.get("drapeau_seuil") or "", ""),
                    (r.get("interpretation") or "").strip(),
                ] if x
            )
            lignes.append([
                e.get("test_nom") or "",
                r.get("sous_epreuve") or "",
                r.get("score_brut") or "",
                etalonnage_texte(r),
                interpretation,
            ])
    return lignes or None


def est_brouillon(b: dict) -> bool:
    """Un bilan qui n'a pas été explicitement validé (ou envoyé) reste un
    brouillon — y compris un bilan vide, qui s'exportait jusqu'ici avec
    en-tête, date et bloc de signature."""
    return (b.get("statut") or "brouillon") not in ("valide", "envoye")


def _content(b: dict, cfg: dict | None = None) -> list[tuple[str, object]]:
    """Document sous forme de blocs (type, contenu), rendus par chaque format."""
    prat = ((cfg or {}).get("praticien")) or {}
    blocks: list[tuple[str, object]] = []
    if est_brouillon(b):
        blocks.append(("brouillon", MENTION_BROUILLON))
    entete = _entete_praticien(prat)
    if entete:
        blocks.append(("entete", entete))
    dest = _destinataire(b)
    if dest:
        blocks.append(("dest", dest))
    doms = b.get("domaine_titres") or "Générique"
    blocks.append(("h1", "Compte-rendu de bilan orthophonique"))
    blocks.append(("p", f"{_TYPE_LBL.get(b.get('type'), b.get('type', ''))} · Domaine(s) : {doms}"))
    patient = _patient_ligne(b)
    if patient:
        blocks.append(("p", patient))
    if (b.get("date_bilan") or "").strip():
        blocks.append(("p", f"Date du bilan : {date_fr(b['date_bilan'])}"))
    for s in b.get("sections", []):
        if (s.get("contenu") or "").strip():
            blocks.append(("h2", s["titre"]))
            # Contenu de rubrique : texte riche (gras, listes…) — voir texte_riche.
            blocks.append(("riche", s["contenu"].strip()))
    table = _table_epreuves(b)
    if table:
        blocks.append(("h2", "Résultats des épreuves"))
        blocks.append(("table", table))
    cot = b.get("cotation")
    if cot:
        # Le code est reconstruit depuis le coefficient plutôt que repris tel
        # quel : les cotations déjà enregistrées portent « AMO 24.0 ». C'est le
        # seul chiffre du document que l'Assurance maladie peut recouper.
        coeff = cotation.coeff_texte(cot["coefficient"])
        blocks.append(("h2", "Cotation (NGAP)"))
        blocks.append((
            "p",
            f"AMO {coeff} — {cotation.euros(cot['montant'])} "
            f"(coefficient {coeff}, valeur lettre-clé "
            f"{cotation.euros(cot['valeur_lettre_cle'])})",
        ))
    sign = _signature(b, prat)
    if sign:
        blocks.append(("sign", sign))
    blocks.append(("hr", ""))
    blocks.append(("i", DISCLAIMER))
    return blocks


def _cellule_md(v: str) -> str:
    """Cellule de tableau Markdown : ni « | » ni retour à la ligne.

    Une interprétation dictée en contenant cassait la table entière — et le
    .md est le format par défaut de la route d'export."""
    v = (v or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()
    return v or "—"


def _cellule_txt(v: str) -> str:
    """Cellule de tableau en texte brut : les colonnes sont alignées au
    caractère, un retour à la ligne décalerait tout ce qui suit."""
    v = (v or "").replace("\r", " ").replace("\n", " ").strip()
    return v or "—"


def to_markdown(b: dict, cfg: dict | None = None) -> str:
    out: list[str] = []
    for k, t in _content(b, cfg):
        if k == "brouillon":
            out.append(f"> **{t}**")
        elif k == "entete":
            out.append("\n".join(f"**{ligne}**" if i == 0 else ligne
                                 for i, ligne in enumerate(t)))
            out.append("\n---")
        elif k == "dest":
            out.append(f"\n{t}")
        elif k == "h1":
            out.append(f"\n# {t}")
        elif k == "h2":
            out.append(f"\n## {t}")
        elif k == "p":
            out.append(f"\n{t}")
        elif k == "riche":
            out.append("\n" + texte_riche.canonique(t))
        elif k == "table":
            out.append("\n| " + " | ".join(_COLONNES) + " |")
            out.append("| " + " | ".join("---" for _ in _COLONNES) + " |")
            for ligne in t:
                out.append("| " + " | ".join(_cellule_md(c) for c in ligne) + " |")
        elif k == "sign":
            out.append("\n" + "  \n".join(t))
        elif k == "hr":
            out.append("\n---")
        elif k == "i":
            out.append(f"\n_{t}_")
    return "\n".join(out).strip() + "\n"


def to_txt(b: dict, cfg: dict | None = None) -> str:
    out: list[str] = []
    for k, t in _content(b, cfg):
        if k == "brouillon":
            out.append(t)
            out.append("=" * 40)
        elif k == "entete":
            out.extend(t)
            out.append("-" * 40)
        elif k == "dest":
            out.append("\n" + t)
        elif k in ("h1", "h2"):
            out.append("\n" + t.upper())
        elif k == "p":
            out.append(t)
        elif k == "riche":
            out.append(texte_riche.en_clair(t))
        elif k == "table":
            cellules = [[_cellule_txt(c) for c in ligne] for ligne in t]
            larg = [
                max(len(_COLONNES[i]), *(len(ligne[i]) for ligne in cellules))
                for i in range(len(_COLONNES))
            ]
            out.append("  ".join(c.ljust(larg[i]) for i, c in enumerate(_COLONNES)))
            out.append("  ".join("-" * w for w in larg))
            for ligne in cellules:
                out.append("  ".join(c.ljust(larg[i]) for i, c in enumerate(ligne)))
        elif k == "sign":
            out.append("")
            out.extend(t)
        elif k == "hr":
            out.append("-" * 40)
        elif k == "i":
            out.append(t)
    return "\n".join(out).strip() + "\n"


def _docx_runs(paragraphe, segments: list[texte_riche.Segment]) -> None:
    """Segments -> runs Word (gras, italique, souligné, retours à la ligne)."""
    for s in segments:
        for i, morceau in enumerate(s.texte.split("\n")):
            if i:
                paragraphe.add_run().add_break()
            if not morceau:
                continue
            run = paragraphe.add_run(morceau)
            if s.gras:
                run.bold = True
            if s.italique:
                run.italic = True
            if s.souligne:
                run.underline = True


def _docx_numerotation_neuve(doc, nom_style: str):
    """Nouvelle instance de numérotation repartant à 1, calquée sur le style.

    python-docx fait partager à tous les paragraphes « List Number » une même
    numérotation : la deuxième liste du document continuait à 4. Retourne
    l'identifiant à poser sur les paragraphes, ou None si le document (un
    gabarit du praticien, par exemple) ne s'y prête pas — la liste continue
    alors, plutôt que d'échouer."""
    try:
        from docx.oxml.ns import qn

        style = doc.styles[nom_style]
        num_id = style.element.pPr.numPr.numId.val
        numbering = doc.part.numbering_part.element
        origine = numbering.num_having_numId(num_id)
        neuf = numbering.add_num(origine.abstractNumId.val)
        neuf.add_lvlOverride(ilvl=0).add_startOverride(1)
        qn("w:numId")  # import utilisé : garde le linter tranquille
        return neuf.numId
    except Exception:
        return None


def _docx_liste(doc, bloc: texte_riche.Liste) -> None:
    nom_style = "List Number" if bloc.ordonnee else "List Bullet"
    num_id = _docx_numerotation_neuve(doc, nom_style) if bloc.ordonnee else None
    for i, item in enumerate(bloc.items, 1):
        try:
            p = doc.add_paragraph(style=nom_style)
        except KeyError:
            # Style absent (gabarit personnalisé) : le marqueur devient du texte.
            p = doc.add_paragraph(f"{i}. " if bloc.ordonnee else "- ")
        else:
            if num_id is not None:
                num_pr = p._p.get_or_add_pPr().get_or_add_numPr()
                num_pr.get_or_add_numId().val = num_id
                num_pr.get_or_add_ilvl().val = 0
        _docx_runs(p, item)


def _docx_riche(doc, texte: str) -> None:
    for bloc in texte_riche.analyser(texte):
        if isinstance(bloc, texte_riche.Liste):
            _docx_liste(doc, bloc)
        else:
            _docx_runs(doc.add_paragraph(), bloc.segments)


def to_docx(b: dict, cfg: dict | None = None) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    for k, t in _content(b, cfg):
        if k == "brouillon":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run(t).bold = True
        elif k == "entete":
            for i, ligne in enumerate(t):
                p = doc.add_paragraph()
                run = p.add_run(ligne)
                run.bold = i == 0
                run.font.size = None if i == 0 else run.font.size
        elif k == "dest":
            p = doc.add_paragraph(t)
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif k == "h1":
            doc.add_heading(t, level=0)
        elif k == "h2":
            doc.add_heading(t, level=1)
        elif k == "p":
            doc.add_paragraph(t)
        elif k == "riche":
            _docx_riche(doc, t)
        elif k == "table":
            table = doc.add_table(rows=1, cols=len(_COLONNES))
            table.style = "Table Grid"
            for i, titre in enumerate(_COLONNES):
                table.rows[0].cells[i].paragraphs[0].add_run(titre).bold = True
            for ligne in t:
                cells = table.add_row().cells
                for i, val in enumerate(ligne):
                    cells[i].text = val or "—"
        elif k == "sign":
            doc.add_paragraph()
            for ligne in t:
                p = doc.add_paragraph(ligne)
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            # Espace laissé à la signature manuscrite ou au cachet.
            doc.add_paragraph()
            doc.add_paragraph()
        elif k == "hr":
            doc.add_paragraph("_" * 30)
        elif k == "i":
            p = doc.add_paragraph()
            p.add_run(t).italic = True
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def to_pdf(b: dict, cfg: dict | None = None) -> bytes:
    """PDF paginé, format d'envoi habituel d'un compte-rendu au prescripteur.

    reportlab est retenu pour rester compatible avec l'exécutable Windows :
    c'est une bibliothèque Python pure, sans moteur de rendu HTML ni binaire
    système à embarquer."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    ss = getSampleStyleSheet()
    corps = ParagraphStyle("corps", parent=ss["BodyText"], fontSize=10, leading=14)
    petit = ParagraphStyle("petit", parent=corps, fontSize=8.5, leading=11)
    droite = ParagraphStyle("droite", parent=corps, alignment=TA_RIGHT)
    centre = ParagraphStyle("centre", parent=corps, alignment=TA_CENTER)
    titre1 = ParagraphStyle("t1", parent=ss["Heading1"], fontSize=15, spaceBefore=10)
    titre2 = ParagraphStyle("t2", parent=ss["Heading2"], fontSize=12, spaceBefore=10)

    def esc(txt: str) -> str:
        return (txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def balise(segments: list[texte_riche.Segment]) -> str:
        """Segments -> balisage de paragraphe reportlab (texte échappé d'abord :
        seules NOS balises passent)."""
        parts = []
        for s in segments:
            t = esc(s.texte).replace("\n", "<br/>")
            if s.souligne:
                t = f"<u>{t}</u>"
            if s.italique:
                t = f"<i>{t}</i>"
            if s.gras:
                t = f"<b>{t}</b>"
            parts.append(t)
        return "".join(parts)

    def riche(texte: str) -> list:
        flow: list = []
        for bloc in texte_riche.analyser(texte):
            if isinstance(bloc, texte_riche.Paragraphe):
                flow.append(Paragraph(balise(bloc.segments), corps))
                continue
            items = [ListItem(Paragraph(balise(i), corps), leftIndent=14) for i in bloc.items]
            flow.append(ListFlowable(
                items, bulletType="1" if bloc.ordonnee else "bullet",
                start=1 if bloc.ordonnee else "•", leftIndent=14,
                bulletFontSize=9, spaceBefore=2, spaceAfter=2,
            ))
        return flow

    def construire(tableau_en_lignes: bool) -> list:
        """Blocs du document. `tableau_en_lignes` rend les résultats sous forme
        de paragraphes plutôt que de tableau : c'est le repli quand une cellule
        est plus haute qu'une page (reportlab ne sait pas la découper)."""
        flow: list = []
        for k, t in _content(b, cfg):
            if k == "brouillon":
                flow.append(Paragraph(f"<b>{esc(t)}</b>", centre))
                flow.append(Spacer(1, 6))
            elif k == "entete":
                for i, ligne in enumerate(t):
                    flow.append(Paragraph(
                        f"<b>{esc(ligne)}</b>" if i == 0 else esc(ligne),
                        corps if i == 0 else petit,
                    ))
                flow.append(Spacer(1, 4))
                flow.append(HRFlowable(width="100%", color=colors.grey))
            elif k == "dest":
                flow.append(Spacer(1, 8))
                flow.append(Paragraph(esc(t), droite))
            elif k == "h1":
                flow.append(Paragraph(esc(t), titre1))
            elif k == "h2":
                flow.append(Paragraph(esc(t), titre2))
            elif k == "p":
                flow.append(Paragraph(esc(t).replace("\n", "<br/>"), corps))
            elif k == "riche":
                # Les rubriques portent gras, listes et sauts de ligne signifiants.
                flow.extend(riche(t))
            elif k == "table" and tableau_en_lignes:
                for ligne in t:
                    parts = [f"<b>{esc(ligne[0])}</b>"] + [
                        f"{esc(_COLONNES[i])} : {esc(v)}"
                        for i, v in enumerate(ligne) if i and v
                    ]
                    flow.append(Paragraph(" — ".join(parts), petit))
            elif k == "table":
                data = [[Paragraph(f"<b>{esc(c)}</b>", petit) for c in _COLONNES]]
                data += [[Paragraph(esc(c or "—"), petit) for c in ligne] for ligne in t]
                table = Table(
                    data, colWidths=[32 * mm, 38 * mm, 28 * mm, 28 * mm, 40 * mm],
                    repeatRows=1,
                )
                table.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                flow.append(table)
            elif k == "sign":
                flow.append(Spacer(1, 16))
                for ligne in t:
                    flow.append(Paragraph(esc(ligne), droite))
                flow.append(Spacer(1, 24))  # place pour la signature ou le cachet
            elif k == "hr":
                flow.append(Spacer(1, 8))
                flow.append(HRFlowable(width="100%", color=colors.grey))
            elif k == "i":
                flow.append(Paragraph(f"<i>{esc(t)}</i>", petit))
        return flow

    def filigrane(canvas, doc):
        """« BROUILLON » en travers de chaque page tant que le bilan n'est pas
        validé : la mention doit rester lisible même sur une page imprimée
        isolément du reste du document."""
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 64)
        canvas.setFillGray(0.85)
        canvas.translate(A4[0] / 2, A4[1] / 2)
        canvas.rotate(45)
        canvas.drawCentredString(0, 0, "BROUILLON")
        canvas.restoreState()

    def document(buf):
        return SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=20 * mm, rightMargin=20 * mm,
            topMargin=18 * mm, bottomMargin=18 * mm,
            title="Compte-rendu de bilan orthophonique",
        )

    pages = {"onFirstPage": filigrane, "onLaterPages": filigrane} if est_brouillon(b) else {}
    buf = io.BytesIO()
    try:
        document(buf).build(construire(False), **pages)
    except Exception:
        # Une cellule plus haute qu'une page fait échouer toute la mise en page
        # (LayoutError) : une interprétation clinique un peu longue suffisait à
        # rendre le PDF impossible. Le document part quand même, résultats
        # rendus en lignes — mieux vaut une mise en forme dégradée qu'un export
        # refusé au moment de l'envoyer au prescripteur.
        buf = io.BytesIO()
        document(buf).build(construire(True), **pages)
    return buf.getvalue()
