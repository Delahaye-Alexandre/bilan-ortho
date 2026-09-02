"""Cotation NGAP (paramétrable). Les valeurs évoluent par avenants — source de
vérité : ameli.fr. Ne rien coder en dur : tout vient de la config."""
from __future__ import annotations

_COEFF_KEY = {
    "initial_simple": "bilan_simple_coeff",
    "initial_complexe": "bilan_complexe_coeff",
    "renouvellement": "renouvellement_coeff",
}


def coeff_texte(v) -> str:
    """Coefficient tel qu'il s'écrit sur une feuille de soins : « AMO 24 ».

    Le front renvoie tous les champs de cotation à chaque enregistrement des
    Paramètres, où Pydantic coerce 24 en 24.0 : le document imprimait « AMO
    24.0 », qui n'est pas une notation NGAP. La décimale n'est conservée que
    lorsqu'elle existe (et s'écrit alors avec une virgule)."""
    f = float(v)
    if f == int(f):
        return str(int(f))
    return f"{f:g}".replace(".", ",")


def euros(v) -> str:
    """Montant à la française : « 62,40 € » (et non « 62.4 € »)."""
    return f"{float(v):.2f}".replace(".", ",") + " €"


def compute(cfg: dict, bilan_type: str) -> dict:
    c = cfg["cotation"]
    coeff = c[_COEFF_KEY.get(bilan_type, "bilan_simple_coeff")]
    valeur = c["valeur_amo"]
    return {
        "code_amo": f"AMO {coeff_texte(coeff)}",
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
