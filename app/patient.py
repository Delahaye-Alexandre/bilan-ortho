"""Gestion des patients : identité minimale, rattachement des bilans,
effacement RGPD (suppression en cascade), calcul d'âge pour les étalonnages.

Minimisation : les fonctions d'audit ne reçoivent jamais le nom du patient,
seulement son identifiant.
"""
from __future__ import annotations

import re
from datetime import date

from .db import dicts as _dicts

# --- dates & âge --------------------------------------------------------------

def _parse_date(s: str | None) -> date | None:
    """Accepte ISO (AAAA-MM-JJ, éventuellement suivi d'une heure) ou JJ/MM/AAAA."""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
        if not m:
            return None
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def date_fr(s: str | None) -> str:
    d = _parse_date(s)
    return d.strftime("%d/%m/%Y") if d else (s or "")


def age_texte(date_naissance: str | None, ref: str | None = None) -> str:
    """Âge en clair (« 8 ans et 3 mois ») à la date ``ref`` (défaut aujourd'hui).
    Chaîne vide si la date de naissance est absente/invalide/future."""
    dn = _parse_date(date_naissance)
    dr = _parse_date(ref) or date.today()
    if not dn or dr < dn:
        return ""
    mois = (dr.year - dn.year) * 12 + (dr.month - dn.month)
    if dr.day < dn.day:
        mois -= 1
    ans, m = divmod(mois, 12)
    an_txt = f"{ans} an{'s' if ans > 1 else ''}"
    mois_txt = f"{m} mois"
    if ans and m:
        return f"{an_txt} et {mois_txt}"
    return an_txt if ans else mois_txt


# --- CRUD -----------------------------------------------------------------------

def create(
    con, nom: str, prenom: str = "", date_naissance: str = "",
    sexe: str = "", notes: str = "",
) -> int:
    return con.execute(
        "INSERT INTO patient(nom, prenom, date_naissance, sexe, notes) VALUES(?,?,?,?,?)",
        (nom.strip(), prenom.strip(), date_naissance.strip(), sexe.strip(), notes.strip()),
    ).lastrowid


def get(con, patient_id: int) -> dict | None:
    rows = _dicts(con.execute("SELECT * FROM patient WHERE id=?", (patient_id,)))
    return rows[0] if rows else None


def liste(con) -> list[dict]:
    """Patients + nombre de bilans rattachés (tri alphabétique)."""
    return _dicts(con.execute(
        "SELECT p.*, (SELECT count(*) FROM bilan b WHERE b.patient_id = p.id) AS nb_bilans "
        "FROM patient p ORDER BY p.nom COLLATE NOCASE, p.prenom COLLATE NOCASE"
    ))


def update(
    con, patient_id: int, nom: str, prenom: str = "", date_naissance: str = "",
    sexe: str = "", notes: str = "",
) -> bool:
    cur = con.execute(
        "UPDATE patient SET nom=?, prenom=?, date_naissance=?, sexe=?, notes=? WHERE id=?",
        (nom.strip(), prenom.strip(), date_naissance.strip(), sexe.strip(),
         notes.strip(), patient_id),
    )
    return cur.rowcount > 0


def delete(con, patient_id: int) -> bool:
    """Effacement RGPD : le patient ET tous ses bilans (cascade : sections,
    épreuves, résultats, dictées, cotations, envois, prescriptions,
    consentements suivent via les clés étrangères)."""
    cur = con.execute("DELETE FROM patient WHERE id=?", (patient_id,))
    return cur.rowcount > 0
