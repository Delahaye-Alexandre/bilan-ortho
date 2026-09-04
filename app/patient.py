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


# Remise de la mention d'information (RGPD art. 13 : enregistrement vocal,
# assistant d'IA local) : une ligne de la table `consentement`, type
# « information », statut « remise », datée du jour de la case cochée. Ce n'est
# pas un consentement — le soin n'en exige pas — mais la trace, par patient,
# que l'information a été donnée (obligation de responsabilité, art. 5.2).
_INFORMATION = (
    "(SELECT min(c.date) FROM consentement c WHERE c.patient_id = p.id "
    "AND c.type = 'information' AND c.statut = 'remise') AS informe_le"
)


def get(con, patient_id: int) -> dict | None:
    rows = _dicts(con.execute(
        f"SELECT p.*, {_INFORMATION} FROM patient p WHERE p.id=?", (patient_id,)
    ))
    return rows[0] if rows else None


def liste(con) -> list[dict]:
    """Patients + nombre de bilans et d'extraits de style rattachés, et date
    de remise de la mention d'information.

    Le décompte des extraits sert à annoncer exactement ce qu'un effacement
    RGPD va emporter, avant de le déclencher."""
    return _dicts(con.execute(
        "SELECT p.*, "
        "(SELECT count(*) FROM bilan b WHERE b.patient_id = p.id) AS nb_bilans, "
        "(SELECT count(*) FROM bilan_reference r WHERE r.patient_id = p.id) "
        f"AS nb_references, {_INFORMATION} "
        "FROM patient p ORDER BY p.nom COLLATE NOCASE, p.prenom COLLATE NOCASE"
    ))


def set_information(con, patient_id: int, remise: bool) -> None:
    """Enregistre (ou retire) la remise de la mention d'information au
    patient. La date de première remise est conservée : cocher deux fois ne
    la rajeunit pas ; décocher efface la trace (case cochée par erreur)."""
    if remise:
        deja = con.execute(
            "SELECT 1 FROM consentement WHERE patient_id=? AND type='information' "
            "AND statut='remise'", (patient_id,)
        ).fetchone()
        if not deja:
            con.execute(
                "INSERT INTO consentement(patient_id, type, date, texte, statut) "
                "VALUES(?, 'information', ?, ?, 'remise')",
                (patient_id, date.today().isoformat(),
                 "Mention d'information remise (enregistrement vocal, assistant d'IA local)"),
            )
    else:
        con.execute(
            "DELETE FROM consentement WHERE patient_id=? AND type='information'",
            (patient_id,),
        )


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
    consentements suivent via les clés étrangères).

    Les extraits de style rattachés à ce patient partent aussi : la cascade ne
    suffirait pas, car leur index vectoriel est une table virtuelle sans
    contrainte de clé étrangère. Sans cela, l'app répondait « effacé » et le
    texte intégral du bilan restait indexé — puis réinjectable dans le prompt
    d'un autre dossier."""
    from . import rag

    rag.delete_par_patient(con, patient_id)
    cur = con.execute("DELETE FROM patient WHERE id=?", (patient_id,))
    return cur.rowcount > 0
