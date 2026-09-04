"""Les documents de conformité citent le code par symbole (`fichier.py::symbole`).

Une citation « fichier:ligne » se périme à la première retouche : la revue du
2026-08-11 en avait relevé une dizaine, dans un document opposable, qui
pointaient sur autre chose que ce qu'elles affirmaient. Ici, chaque symbole
cité doit exister dans le fichier cité, et plus aucune citation par numéro de
ligne n'est admise.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
DOCS = [
    RACINE / "docs/conformite/ai-act-auto-evaluation.md",
    RACINE / "docs/conformite/declaration-finalite-mdr.md",
    RACINE / "docs/RGPD-registre-traitements.md",
    RACINE / "docs/notice-medico-legale.md",
    RACINE / "docs/notice-usage-ia.md",
    RACINE / "docs/mention-information-patient.md",
    RACINE / "docs/verifier-que-rien-ne-sort.md",
    RACINE / "docs/installation.md",
    RACINE / "docs/guide-test.md",
    RACINE / "README.md",
    RACINE / "SECURITY.md",
]
CITATION = re.compile(r"`([\w./-]+\.py)::([\w.]+)`")
PAR_NUMERO_DE_LIGNE = re.compile(r"`[\w./-]+\.(?:py|sh|html):\d[\d,-]*`")


def _citations() -> list[tuple[str, str, str]]:
    out = []
    for doc in DOCS:
        for m in CITATION.finditer(doc.read_text(encoding="utf-8")):
            out.append((doc.name, m.group(1), m.group(2)))
    return out


@pytest.mark.parametrize(("doc", "fichier", "symbole"), _citations())
def test_symbole_cite_existe(doc, fichier, symbole):
    chemin = RACINE / fichier
    assert chemin.exists(), f"{doc} cite {fichier}, qui n'existe pas"
    source = chemin.read_text(encoding="utf-8")
    for partie in symbole.split("."):
        assert re.search(rf"\b{re.escape(partie)}\b", source), (
            f"{doc} cite {fichier}::{symbole} — « {partie} » est absent du fichier"
        )


def test_aucune_citation_par_numero_de_ligne():
    for doc in DOCS:
        m = PAR_NUMERO_DE_LIGNE.search(doc.read_text(encoding="utf-8"))
        assert m is None, f"{doc.name} cite le code par numéro de ligne ({m.group(0)})"


def test_les_documents_citent_bien_le_code():
    """Garde-fou du garde-fou : si la syntaxe des citations changeait, le test
    paramétré ci-dessus passerait à vide."""
    assert len(_citations()) >= 20
