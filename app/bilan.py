"""Persistance et logique métier d'un bilan (rubriques, structuration).

Toutes les fonctions prennent une connexion chiffrée ``con`` (obtenue via
``security.transaction()``). Les appels au LLM (asynchrones) restent dans les
endpoints ; ce module ne fait que du CRUD/persistance.
"""
from __future__ import annotations

import json
import re

from . import config, db
from .db import dicts as _dicts


def domaine_titres(domaines: list[str]) -> str:
    m = {d["cle"]: d["titre"] for d in config.DOMAINES}
    return ", ".join(m.get(c, c) for c in domaines)


def _trame(cfg: dict | None) -> list[tuple[str, str]]:
    """Trame effective : sections de la config (validées) ou tronc commun."""
    sections = ((cfg or {}).get("trame") or {}).get("sections") or []
    valides = [
        (s["cle"], s["titre"])
        for s in sections
        if isinstance(s, dict) and s.get("cle") and s.get("titre")
    ]
    return valides or db.SECTIONS_TRONC_COMMUN


def create(
    con,
    domaines: list[str],
    type_: str = "initial_simple",
    patient_id: int | None = None,
    motif: str = "",
    cfg: dict | None = None,
) -> int:
    cur = con.execute(
        "INSERT INTO bilan(patient_id, domaines, type, motif) VALUES(?,?,?,?)",
        (patient_id, json.dumps(domaines), type_, motif),
    )
    bid = cur.lastrowid
    for ordre, (cle, titre) in enumerate(_trame(cfg)):
        con.execute(
            "INSERT INTO section(bilan_id, cle, titre, ordre) VALUES(?,?,?,?)",
            (bid, cle, titre, ordre),
        )
    return bid


def set_statut(con, bilan_id: int, statut: str, destinataire: str = "") -> bool:
    """Fait évoluer le statut du bilan (brouillon → validé → envoyé).

    Un passage à « envoye » trace l'envoi au prescripteur (table envoi) —
    seulement au premier passage : re-cliquer « envoyé » ne doit pas dupliquer
    la trace."""
    row = con.execute("SELECT statut FROM bilan WHERE id=?", (bilan_id,)).fetchone()
    if row is None:
        return False
    ancien = row[0]
    con.execute(
        "UPDATE bilan SET statut=?, updated_at=datetime('now') WHERE id=?",
        (statut, bilan_id),
    )
    if statut == "envoye" and ancien != "envoye":
        con.execute(
            "INSERT INTO envoi(bilan_id, destinataire, horodatage, canal) "
            "VALUES(?,?,datetime('now'),'manuel')",
            (bilan_id, destinataire),
        )
    return True


def get(con, bilan_id: int) -> dict | None:
    rows = _dicts(con.execute("SELECT * FROM bilan WHERE id=?", (bilan_id,)))
    if not rows:
        return None
    b = rows[0]
    b["domaines"] = json.loads(b.get("domaines") or "[]")
    b["domaine_titres"] = domaine_titres(b["domaines"])
    b["patient"] = None
    if b.get("patient_id"):
        p = _dicts(con.execute("SELECT * FROM patient WHERE id=?", (b["patient_id"],)))
        b["patient"] = p[0] if p else None
    b["sections"] = _dicts(
        con.execute("SELECT * FROM section WHERE bilan_id=? ORDER BY ordre", (bilan_id,))
    )
    eps = _dicts(
        con.execute("SELECT * FROM epreuve WHERE bilan_id=? ORDER BY id", (bilan_id,))
    )
    for e in eps:
        e["resultats"] = _dicts(
            con.execute("SELECT * FROM resultat WHERE epreuve_id=? ORDER BY id", (e["id"],))
        )
    b["epreuves"] = eps
    cot = _dicts(con.execute("SELECT * FROM cotation WHERE bilan_id=?", (bilan_id,)))
    b["cotation"] = cot[0] if cot else None
    return b


def liste(con, limit: int = 20, offset: int = 0) -> list[dict]:
    rows = _dicts(
        con.execute(
            "SELECT b.id, b.domaines, b.type, b.statut, b.motif, b.created_at, "
            "b.patient_id, p.nom AS patient_nom, p.prenom AS patient_prenom "
            "FROM bilan b LEFT JOIN patient p ON p.id = b.patient_id "
            "ORDER BY b.id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    )
    for r in rows:
        r["domaines"] = json.loads(r.get("domaines") or "[]")
        r["domaine_titres"] = domaine_titres(r["domaines"])
    return rows


def apply_updates(con, bilan_id: int, updates: list[dict], source: str = "dictee") -> int:
    """Ajoute les textes proposés aux rubriques correspondantes (statut propose_ia)."""
    applied = 0
    for u in updates:
        row = con.execute(
            "SELECT id, contenu FROM section WHERE bilan_id=? AND cle=?",
            (bilan_id, u["section"]),
        ).fetchone()
        if not row:
            continue
        sid, contenu = row[0], (row[1] or "")
        nouveau = (contenu + ("\n\n" if contenu else "") + u["texte"]).strip()
        con.execute(
            "UPDATE section SET contenu=?, statut='propose_ia', source=?, "
            "updated_at=datetime('now') WHERE id=?",
            (nouveau, source, sid),
        )
        applied += 1
    con.execute("UPDATE bilan SET updated_at=datetime('now') WHERE id=?", (bilan_id,))
    return applied


def update_section(
    con, bilan_id: int, cle: str, contenu: str, statut: str | None = None
) -> bool:
    if statut:
        cur = con.execute(
            "UPDATE section SET contenu=?, statut=?, source='manuel', "
            "updated_at=datetime('now') WHERE bilan_id=? AND cle=?",
            (contenu, statut, bilan_id, cle),
        )
    else:
        cur = con.execute(
            "UPDATE section SET contenu=?, source='manuel', "
            "updated_at=datetime('now') WHERE bilan_id=? AND cle=?",
            (contenu, bilan_id, cle),
        )
    if cur.rowcount:
        # Sans cela, un bilan édité uniquement rubrique par rubrique restait
        # « inactif » aux yeux de la purge de conservation RGPD.
        con.execute(
            "UPDATE bilan SET updated_at=datetime('now') WHERE id=?", (bilan_id,)
        )
    return cur.rowcount > 0


# --- Saisie structurée des résultats + interprétation d'étalonnage ----------

DRAPEAU_LIBELLE = {
    "norme": "dans la norme",
    "fragilite": "zone de fragilité",
    "pathologique": "sous le seuil pathologique",
    "severe": "déficit sévère",
}
_ET_LBL = {
    "ecart_type": "ET", "note_standard": "NS",
    "age_dev": "(âge dév.)", "age_lecture": "(âge de lecture)",
}


def _parse_num(v) -> float | None:
    if v is None:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    return float(m.group(0).replace(",", ".")) if m else None


def interpret_drapeau(etalonnage_type: str | None, valeur, cfg: dict) -> str:
    """Déduit norme/fragilité/pathologique/sévère depuis l'étalonnage + seuils config."""
    n = _parse_num(valeur)
    if n is None or not etalonnage_type:
        return ""
    s = cfg["seuils"]
    et = None
    if etalonnage_type == "ecart_type":
        et = n
    elif etalonnage_type == "note_standard":  # moyenne 10, ET 3
        et = (n - 10) / 3.0
    elif etalonnage_type == "percentile":
        # Seuils percentile configurables, comme leurs équivalents écart-type.
        if n <= s.get("severe_percentile", 2):
            return "severe"
        if n <= s.get("pathologique_percentile", 7):
            return "pathologique"
        if n <= s.get("fragilite_percentile", 16):
            return "fragilite"
        return "norme"
    if et is None:
        return ""
    if et <= s["severe_et"]:
        return "severe"
    if et <= s["pathologique_et"]:
        return "pathologique"
    if et <= s["fragilite_et"]:
        return "fragilite"
    return "norme"


def resultat_phrase(test_nom: str, r: dict) -> str:
    """Phrase-type de restitution d'un résultat (déterministe, sans LLM)."""
    tete = test_nom + (f" — {r['sous_epreuve']}" if r.get("sous_epreuve") else "") + " :"
    parts = []
    if r.get("score_brut"):
        parts.append(f"score {r['score_brut']}")
    if r.get("etalonnage_valeur"):
        if r.get("etalonnage_type") == "percentile":
            # collé à la valeur : « 25e percentile », pas « 25 e percentile »
            parts.append(f"{r['etalonnage_valeur']}e percentile")
        else:
            lbl = _ET_LBL.get(r.get("etalonnage_type"), "")
            parts.append(f"{r['etalonnage_valeur']} {lbl}".strip())
    line = tete + (" " + ", ".join(parts) if parts else "")
    drap = r.get("drapeau_seuil")
    if drap in DRAPEAU_LIBELLE:
        line += f" — {DRAPEAU_LIBELLE[drap]}"
    if r.get("interpretation"):
        line += f". {r['interpretation']}"
    return line


def add_epreuve(
    con, bilan_id: int, domaine: str, test_nom: str, version: str,
    resultats: list[dict], cfg: dict,
) -> dict:
    """Enregistre une épreuve + ses résultats (drapeau auto) et ajoute les
    phrases-types à la rubrique « épreuves »."""
    eid = con.execute(
        "INSERT INTO epreuve(bilan_id, domaine, test_nom, version) VALUES(?,?,?,?)",
        (bilan_id, domaine, test_nom, version),
    ).lastrowid
    stored, phrases = [], []
    for r in resultats:
        drap = r.get("drapeau_seuil") or interpret_drapeau(
            r.get("etalonnage_type"), r.get("etalonnage_valeur"), cfg
        )
        con.execute(
            "INSERT INTO resultat(epreuve_id, sous_epreuve, score_brut, etalonnage_type, "
            "etalonnage_valeur, percentile, note_standard, age_dev, interpretation, drapeau_seuil) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (eid, r.get("sous_epreuve"), r.get("score_brut"), r.get("etalonnage_type"),
             r.get("etalonnage_valeur"), r.get("percentile"), r.get("note_standard"),
             r.get("age_dev"), r.get("interpretation"), drap),
        )
        rr = {**r, "drapeau_seuil": drap}
        stored.append(rr)
        phrases.append(resultat_phrase(test_nom, rr))
    if phrases:
        row = con.execute(
            "SELECT id, contenu FROM section WHERE bilan_id=? AND cle='epreuves'", (bilan_id,)
        ).fetchone()
        if row:
            contenu = (row[1] or "")
            nouveau = (contenu + ("\n" if contenu else "") + "\n".join(phrases)).strip()
            con.execute(
                "UPDATE section SET contenu=?, statut='propose_ia', source='structured', "
                "updated_at=datetime('now') WHERE id=?",
                (nouveau, row[0]),
            )
    con.execute("UPDATE bilan SET updated_at=datetime('now') WHERE id=?", (bilan_id,))
    return {"id": eid, "test_nom": test_nom, "domaine": domaine,
            "version": version, "resultats": stored}
