"""Cotation NGAP (paramétrable). Les valeurs évoluent par avenants — source de
vérité : ameli.fr. Ne rien coder en dur : tout vient de la config."""
from __future__ import annotations

_COEFF_KEY = {
    "initial_simple": "bilan_simple_coeff",
    "initial_complexe": "bilan_complexe_coeff",
    "renouvellement": "renouvellement_coeff",
}


def compute(cfg: dict, bilan_type: str) -> dict:
    c = cfg["cotation"]
    coeff = c[_COEFF_KEY.get(bilan_type, "bilan_simple_coeff")]
    valeur = c["valeur_amo"]
    return {
        "code_amo": f"AMO {coeff}",
        "coefficient": float(coeff),
        "valeur_lettre_cle": float(valeur),
        "montant": round(float(coeff) * float(valeur), 2),
    }


def set_for_bilan(con, bilan_id: int, cot: dict) -> None:
    con.execute("DELETE FROM cotation WHERE bilan_id=?", (bilan_id,))
    con.execute(
        "INSERT INTO cotation(bilan_id, code_amo, coefficient, valeur_lettre_cle, montant) "
        "VALUES(?,?,?,?,?)",
        (bilan_id, cot["code_amo"], cot["coefficient"], cot["valeur_lettre_cle"], cot["montant"]),
    )
