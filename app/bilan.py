"""Persistance et logique métier d'un bilan (rubriques, structuration).

Toutes les fonctions prennent une connexion chiffrée ``con`` (obtenue via
``security.transaction()``). Les appels au LLM (asynchrones) restent dans les
endpoints ; ce module ne fait que du CRUD/persistance.
"""
from __future__ import annotations

import json
import re
import unicodedata

from . import config, db
from .db import dicts as _dicts
from .texte_riche import sans_controles


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
    date_bilan: str = "",
    prescripteur: str = "",
    prescripteur_rpps: str = "",
) -> int:
    # La colonne `date_bilan` existait mais restait nulle : l'export ne portait
    # donc aucune date, alors qu'un compte-rendu adressé au prescripteur doit
    # être daté. Vide = aujourd'hui, modifiable ensuite (un CR peut être rédigé
    # plusieurs jours après la séance).
    cur = con.execute(
        "INSERT INTO bilan(patient_id, domaines, type, motif, date_bilan) "
        "VALUES(?,?,?,?,COALESCE(NULLIF(?,''), date('now', 'localtime')))",
        (patient_id, json.dumps(domaines), type_, motif, date_bilan),
    )
    bid = cur.lastrowid
    if prescripteur.strip() or prescripteur_rpps.strip():
        set_prescripteur(con, bid, prescripteur, prescripteur_rpps)
    for ordre, (cle, titre) in enumerate(_trame(cfg)):
        con.execute(
            "INSERT INTO section(bilan_id, cle, titre, ordre) VALUES(?,?,?,?)",
            (bid, cle, titre, ordre),
        )
    return bid


def set_prescripteur(
    con, bilan_id: int, nom: str, rpps: str = "", date_prescription: str = ""
) -> None:
    """Rattache le prescripteur au bilan via la table `prescription`.

    Cette table et `bilan.prescription_id` existaient dans le schéma sans
    qu'aucun code ne les remplisse : l'export ne portait donc aucun
    destinataire, alors que le compte-rendu est adressé au médecin qui a
    prescrit le bilan. Une seule prescription par bilan : on remplace."""
    row = con.execute(
        "SELECT prescription_id, patient_id FROM bilan WHERE id=?", (bilan_id,)
    ).fetchone()
    if row is None:
        return
    pres_id, patient_id = row[0], row[1]
    if pres_id:
        con.execute(
            "UPDATE prescription SET prescripteur_nom=?, prescripteur_rpps=?, "
            "date_prescription=? WHERE id=?",
            (nom.strip(), rpps.strip(), date_prescription.strip() or None, pres_id),
        )
        return
    pres_id = con.execute(
        "INSERT INTO prescription(patient_id, prescripteur_nom, prescripteur_rpps, "
        "date_prescription) VALUES(?,?,?,?)",
        (patient_id, nom.strip(), rpps.strip(), date_prescription.strip() or None),
    ).lastrowid
    con.execute("UPDATE bilan SET prescription_id=? WHERE id=?", (pres_id, bilan_id))


def maj_entete(
    con,
    bilan_id: int,
    date_bilan: str | None = None,
    prescripteur: str | None = None,
    prescripteur_rpps: str | None = None,
) -> bool:
    """Met à jour la date du bilan et/ou son prescripteur (None = inchangé)."""
    ligne = con.execute("SELECT date_bilan FROM bilan WHERE id=?", (bilan_id,)).fetchone()
    if ligne is None:
        return False
    avant = (ligne[0], prescripteur_bilan(con, bilan_id))
    if date_bilan is not None:
        con.execute(
            "UPDATE bilan SET date_bilan=COALESCE(NULLIF(?,''), date('now', 'localtime')), "
            "updated_at=datetime('now') WHERE id=?",
            (date_bilan, bilan_id),
        )
    if prescripteur is not None or prescripteur_rpps is not None:
        actuel = avant[1]
        set_prescripteur(
            con,
            bilan_id,
            prescripteur if prescripteur is not None else actuel.get("nom", ""),
            prescripteur_rpps if prescripteur_rpps is not None
            else actuel.get("rpps", ""),
        )
        con.execute(
            "UPDATE bilan SET updated_at=datetime('now') WHERE id=?", (bilan_id,)
        )
    apres = (
        con.execute("SELECT date_bilan FROM bilan WHERE id=?", (bilan_id,)).fetchone()[0],
        prescripteur_bilan(con, bilan_id),
    )
    # La date et le prescripteur sont imprimés sur le document : les corriger
    # après validation change ce qui a été validé. Un enregistrement à
    # l'identique (l'interface enregistre l'en-tête avant chaque export) ne
    # retire rien.
    if apres != avant:
        _contenu_modifie(con, bilan_id)
    return True


def prescripteur_bilan(con, bilan_id: int) -> dict:
    """Prescripteur rattaché au bilan (dict vide si aucun)."""
    row = con.execute(
        "SELECT p.prescripteur_nom, p.prescripteur_rpps, p.date_prescription "
        "FROM bilan b JOIN prescription p ON p.id = b.prescription_id "
        "WHERE b.id=?",
        (bilan_id,),
    ).fetchone()
    if row is None:
        return {}
    return {"nom": row[0] or "", "rpps": row[1] or "", "date": row[2] or ""}


def _contenu_modifie(con, bilan_id: int) -> bool:
    """À appeler après toute modification de ce que le document imprime.

    Met à jour la date de modification (la purge de conservation en dépend) et
    **retire la validation** : un bilan « validé » ou « envoyé » le restait
    après une nouvelle analyse ou une retouche, si bien que l'export sortait
    sans la mention BROUILLON avec un texte proposé par l'IA que personne
    n'avait relu — et qu'un document « envoyé » n'était plus celui qui était
    parti, sans trace. Rend True quand le bilan vient de redevenir un
    brouillon ; le journal d'audit en garde la trace."""
    con.execute("UPDATE bilan SET updated_at=datetime('now') WHERE id=?", (bilan_id,))
    cur = con.execute(
        "UPDATE bilan SET statut='brouillon' WHERE id=? AND statut IN ('valide','envoye')",
        (bilan_id,),
    )
    if cur.rowcount:
        con.execute(
            "INSERT INTO audit_log(action, entite, entite_id, details) VALUES(?,?,?,?)",
            ("statut", "bilan", bilan_id, "brouillon (contenu modifié après validation)"),
        )
    return cur.rowcount > 0


def statut(con, bilan_id: int) -> str | None:
    """Statut du bilan (None s'il n'existe pas)."""
    row = con.execute("SELECT statut FROM bilan WHERE id=?", (bilan_id,)).fetchone()
    return row[0] if row else None


# Une rubrique reste à relire tant qu'elle porte un texte proposé par l'IA que
# l'orthophoniste n'a pas validé, ou un signalement de traçabilité en attente.
_A_RELIRE = (
    "bilan_id=? AND TRIM(COALESCE(contenu,''))!='' "
    "AND (statut='propose_ia' OR signalements IS NOT NULL)"
)


def rubriques_a_relire(con, bilan_id: int) -> list[str]:
    """Intitulés des rubriques encore « à valider » ou signalées.

    « Marquer validé » ne regardait que le bilan : toutes ses rubriques
    pouvaient être des propositions de l'IA jamais relues, signalements « chiffre
    absent de la dictée » compris, et le document sortait sans la mention
    BROUILLON. La validation d'ensemble les exige désormais relues — ou
    l'attestation explicite qu'elles l'ont été (cf. :func:`valider_rubriques`)."""
    return [
        r[0] for r in con.execute(
            f"SELECT titre FROM section WHERE {_A_RELIRE} ORDER BY ordre", (bilan_id,)
        )
    ]


def valider_rubriques(con, bilan_id: int) -> int:
    """Marque validées les rubriques encore à relire : l'orthophoniste vient
    d'attester les avoir relues en validant le bilan entier. Même règle que
    l'enregistrement d'une rubrique : le signalement a joué son rôle."""
    return con.execute(
        f"UPDATE section SET statut='valide', signalements=NULL WHERE {_A_RELIRE}",
        (bilan_id,),
    ).rowcount


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


def _lire_signalements(brut) -> list[str]:
    """Signalements « à vérifier » persistés avec la rubrique (JSON → liste)."""
    if not brut:
        return []
    try:
        valeurs = json.loads(brut)
    except (TypeError, ValueError):
        return []
    return [str(v) for v in valeurs] if isinstance(valeurs, list) else []


def set_signalements(con, bilan_id: int, cle: str, messages: list[str]) -> None:
    """Enregistre (ou efface) les avertissements de traçabilité d'une rubrique.

    Ils portent la promesse centrale du produit — « aucun chiffre inventé » —
    et ne vivaient qu'en mémoire du navigateur : un F5, un verrouillage
    d'inactivité ou un changement de bilan les effaçait, laissant un
    compte-rendu « à valider » sans que rien n'indique où regarder."""
    con.execute(
        "UPDATE section SET signalements=? WHERE bilan_id=? AND cle=?",
        (json.dumps(messages, ensure_ascii=False) if messages else None, bilan_id, cle),
    )


def ajouter_signalements(con, bilan_id: int, cle: str, messages: list[str]) -> None:
    """Ajoute des avertissements à ceux déjà portés par la rubrique.

    `apply_updates` concatène le texte proposé au texte existant : un chiffre
    inventé au tour N reste dans la rubrique au tour N+1. Remplacer la liste
    (au lieu de la compléter) effaçait l'avertissement dès que le fragment
    suivant était propre — et la rubrique redevenait alors une « source »
    légitime pour les tours d'après. Les avertissements ne disparaissent qu'à
    l'enregistrement par l'orthophoniste (`update_section`)."""
    if not messages:
        return
    row = con.execute(
        "SELECT signalements FROM section WHERE bilan_id=? AND cle=?", (bilan_id, cle),
    ).fetchone()
    if not row:
        return
    anciens = json.loads(row[0]) if row[0] else []
    fusion = anciens + [m for m in messages if m not in anciens]
    set_signalements(con, bilan_id, cle, fusion)


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
    for s in b["sections"]:
        s["signalements"] = _lire_signalements(s.get("signalements"))
    eps = _dicts(
        con.execute("SELECT * FROM epreuve WHERE bilan_id=? ORDER BY id", (bilan_id,))
    )
    # Seuils du moment, pour confronter les drapeaux enregistrés d'un brouillon
    # (un document validé ou envoyé reste tel qu'il a été relu).
    cfg_seuils = None
    if eps and b.get("statut") == "brouillon":
        cfg_seuils = config.ConfigStore(con).effective()
    for e in eps:
        e["resultats"] = _dicts(
            con.execute("SELECT * FROM resultat WHERE epreuve_id=? ORDER BY id", (e["id"],))
        )
        # Recalculée à chaque lecture depuis les valeurs enregistrées : l'alerte
        # n'était rendue qu'à la saisie et disparaissait au premier F5, alors
        # que le drapeau du compte-rendu continuait d'en dépendre.
        e["avertissements"] = alertes_plausibilite(e["test_nom"], e["resultats"], cfg_seuils)
    b["epreuves"] = eps
    b["prescripteur"] = prescripteur_bilan(con, bilan_id)
    cot = _dicts(con.execute("SELECT * FROM cotation WHERE bilan_id=?", (bilan_id,)))
    b["cotation"] = cot[0] if cot else None
    return b


def delete(con, bilan_id: int) -> bool:
    """Supprime un bilan et tout ce qui en dépend.

    Sections, épreuves, résultats, cotation, envois et dictées suivent par
    cascade. La prescription, rattachée au patient et non au bilan, est
    supprimée explicitement : sans cela, le nom du médecin survivrait au
    document qu'il concernait. Jusqu'ici, effacer un bilan erroné imposait de
    supprimer le patient entier."""
    row = con.execute(
        "SELECT prescription_id FROM bilan WHERE id=?", (bilan_id,)
    ).fetchone()
    if row is None:
        return False
    con.execute("DELETE FROM bilan WHERE id=?", (bilan_id,))
    if row[0]:
        con.execute("DELETE FROM prescription WHERE id=?", (row[0],))
    return True


def delete_epreuve(con, bilan_id: int, epreuve_id: int) -> bool:
    """Retire une épreuve du bilan (ses résultats suivent par cascade).

    Une échelle d'étalonnage mal choisie produit un drapeau faux, qui part dans
    le tableau du compte-rendu : il faut pouvoir le retirer."""
    cur = con.execute(
        "DELETE FROM epreuve WHERE id=? AND bilan_id=?", (epreuve_id, bilan_id)
    )
    if cur.rowcount:
        _contenu_modifie(con, bilan_id)  # le tableau des résultats change
    return cur.rowcount > 0


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


def _sans_accents(s: str) -> str:
    d = unicodedata.normalize("NFD", s)
    return "".join(c for c in d if unicodedata.category(c) != "Mn")


def _cle_comparaison(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _sans_accents(s).lower())


_PREFIXE_TITRE = re.compile(r"^(?:\*+|<u>)?\s*([^\n:]{1,60}?)\s*(?:\*+|</u>)?\s*:\s*(?:\*+\s*)?")


def nettoyer_prefixe_titre(texte: str, titre: str, cle: str = "") -> str:
    """Retire le « Titre : » que le modèle place spontanément en tête du texte.

    Le titre de la rubrique est déjà affiché dans l'interface et dans l'export :
    le laisser produisait « ## Anamnèse » suivi de « Anamnèse : … » dans chaque
    rubrique de chaque compte-rendu. La consigne le proscrit, ce nettoyage le
    garantit. Seul un préfixe correspondant au titre ou à la clé de LA rubrique
    visée est retiré : « Antécédents familiaux : … » dans l'anamnèse est du
    contenu, et reste intact."""
    tete = _PREFIXE_TITRE.match(texte.lstrip())
    if not tete:
        return texte
    candidat = _cle_comparaison(tete.group(1))
    attendus = {_cle_comparaison(titre), _cle_comparaison(cle)} - {""}
    if candidat and candidat in attendus:
        return texte.lstrip()[tete.end():].lstrip()
    return texte


def _empreinte(transcription: str) -> str:
    import hashlib

    return hashlib.sha256(" ".join(transcription.split()).encode("utf-8")).hexdigest()


def tour_a_remplacer(con, bilan_id: int, transcription: str) -> dict[str, dict]:
    """Rubriques que le passage précédent a remplies à partir de CETTE dictée et
    que personne n'a retouchées depuis : ``{clé: {"avant": …, "apres": …}}``.

    « Relancez l'analyse » (analyse incomplète, passage non rangé) repartait de
    la même dictée et **ajoutait** sa proposition à la précédente : chaque
    rubrique déjà remplie était doublée, parfois avec deux formulations
    contradictoires, à nettoyer à la main. Une relance remplace désormais ce
    que le passage précédent avait proposé. Une rubrique corrigée entre-temps
    n'est pas touchée."""
    if not transcription.strip():
        return {}
    row = con.execute(
        "SELECT empreinte, rubriques FROM tour_analyse WHERE bilan_id=?", (bilan_id,)
    ).fetchone()
    if not row or row[0] != _empreinte(transcription):
        return {}
    try:
        rubriques = json.loads(row[1])
    except (TypeError, ValueError):
        return {}
    actuels = dict(con.execute(
        "SELECT cle, COALESCE(contenu,'') FROM section WHERE bilan_id=?", (bilan_id,)
    ).fetchall())
    return {
        cle: r for cle, r in rubriques.items()
        if isinstance(r, dict) and actuels.get(cle) == r.get("apres")
    }


def retirer_tour(con, bilan_id: int, a_remplacer: dict[str, dict]) -> None:
    """Remet les rubriques dans l'état d'avant le passage précédent."""
    for cle, r in a_remplacer.items():
        con.execute(
            "UPDATE section SET contenu=?, statut=?, signalements=? WHERE bilan_id=? AND cle=?",
            (r.get("avant") or "", r.get("statut_avant") or "vide",
             r.get("signalements_avant"), bilan_id, cle),
        )


def noter_tour(con, bilan_id: int, transcription: str, avant: dict[str, dict]) -> None:
    """Mémorise ce que ce passage a changé (cf. :func:`tour_a_remplacer`).
    ``avant`` : état des rubriques juste avant l'application des propositions."""
    if not transcription.strip():
        return
    rubriques = {}
    for cle, contenu in con.execute(
        "SELECT cle, COALESCE(contenu,'') FROM section WHERE bilan_id=?", (bilan_id,)
    ).fetchall():
        a = avant.get(cle) or {}
        if contenu != (a.get("contenu") or ""):
            rubriques[cle] = {
                "avant": a.get("contenu") or "", "apres": contenu,
                "statut_avant": a.get("statut") or "vide",
                "signalements_avant": a.get("signalements"),
            }
    con.execute(
        "INSERT INTO tour_analyse(bilan_id, empreinte, rubriques) VALUES(?,?,?) "
        "ON CONFLICT(bilan_id) DO UPDATE SET empreinte=excluded.empreinte, "
        "rubriques=excluded.rubriques, created_at=datetime('now')",
        (bilan_id, _empreinte(transcription), json.dumps(rubriques, ensure_ascii=False)),
    )


def etat_rubriques(con, bilan_id: int) -> dict[str, dict]:
    return {
        r[0]: {"contenu": r[1] or "", "statut": r[2], "signalements": r[3]}
        for r in con.execute(
            "SELECT cle, contenu, statut, signalements FROM section WHERE bilan_id=?",
            (bilan_id,),
        )
    }


def apply_updates(
    con, bilan_id: int, updates: list[dict], source: str = "dictee",
) -> int:
    """Ajoute les textes proposés aux rubriques correspondantes (statut propose_ia)."""
    applied = 0
    for u in updates:
        row = con.execute(
            "SELECT id, contenu, titre FROM section WHERE bilan_id=? AND cle=?",
            (bilan_id, u["section"]),
        ).fetchone()
        if not row:
            continue
        sid, contenu = row[0], (row[1] or "")
        texte = nettoyer_prefixe_titre(sans_controles(u["texte"]), row[2] or "", u["section"])
        if not texte.strip():
            continue
        nouveau = (contenu + ("\n\n" if contenu else "") + texte).strip()
        con.execute(
            "UPDATE section SET contenu=?, statut='propose_ia', source=?, "
            "updated_at=datetime('now') WHERE id=?",
            (nouveau, source, sid),
        )
        applied += 1
    con.execute("UPDATE bilan SET updated_at=datetime('now') WHERE id=?", (bilan_id,))
    if applied:
        # Un texte proposé par l'IA vient d'entrer dans un bilan déjà validé :
        # il n'est plus validé.
        _contenu_modifie(con, bilan_id)
    return applied


def update_section(
    con, bilan_id: int, cle: str, contenu: str, statut: str | None = None
) -> bool:
    # Enregistrer une rubrique, c'est l'avoir relue : l'avertissement de
    # traçabilité a joué son rôle et disparaît (même règle que dans l'interface).
    contenu = sans_controles(contenu)
    avant = con.execute(
        "SELECT contenu FROM section WHERE bilan_id=? AND cle=?", (bilan_id, cle)
    ).fetchone()
    if statut:
        cur = con.execute(
            "UPDATE section SET contenu=?, statut=?, source='manuel', "
            "signalements=NULL, updated_at=datetime('now') "
            "WHERE bilan_id=? AND cle=?",
            (contenu, statut, bilan_id, cle),
        )
    else:
        cur = con.execute(
            "UPDATE section SET contenu=?, source='manuel', signalements=NULL, "
            "updated_at=datetime('now') WHERE bilan_id=? AND cle=?",
            (contenu, bilan_id, cle),
        )
    if cur.rowcount:
        # Sans cela, un bilan édité uniquement rubrique par rubrique restait
        # « inactif » aux yeux de la purge de conservation RGPD.
        con.execute(
            "UPDATE bilan SET updated_at=datetime('now') WHERE id=?", (bilan_id,)
        )
        # Seul un texte qui change retire la validation du bilan : valider une
        # rubrique sans y toucher ne modifie pas le document.
        if ((avant[0] if avant else "") or "").strip() != (contenu or "").strip():
            _contenu_modifie(con, bilan_id)
    return cur.rowcount > 0


# --- Saisie structurée des résultats + interprétation d'étalonnage ----------

DRAPEAU_LIBELLE = {
    "norme": "dans la norme",
    "fragilite": "zone de fragilité",
    "pathologique": "sous le seuil pathologique",
    "severe": "déficit sévère",
}
_ET_LBL = {
    "ecart_type": "ET", "note_standard": "NS", "note_standard_100": "NS (moy. 100)",
    "age_dev": "(âge dév.)", "age_lecture": "(âge de lecture)",
}


# Tous les tirets qu'une saisie réelle met devant un nombre : le vrai signe
# moins (U+2212 — celui que l'écran Paramètres affiche lui-même et que portent
# les comptes-rendus des logiciels de tests), les tirets que Word substitue à
# la frappe, les variantes insécables et pleine chasse.
_MOINS = str.maketrans(dict.fromkeys("\u2212\u2013\u2014\u2012\u2010\u2011\ufe63\uff0d", "-"))
_NOMBRE = re.compile(r"([-+])?[ \u00a0\u202f]*(\d+(?:[.,]\d+)?)")


def _parse_num(v) -> float | None:
    """Premier nombre d'une valeur saisie, signe compris.

    « −2,1 », « –2,1 » et « - 2,1 » étaient lus +2,1 : seul le tiret du clavier
    collé au chiffre comptait comme un signe. Un déficit sévère ressortait
    alors « dans la norme » dans le tableau du compte-rendu, sans alerte
    (2,1 est une valeur plausible)."""
    if v is None:
        return None
    m = _NOMBRE.search(str(v).translate(_MOINS))
    if not m:
        return None
    n = float(m.group(2).replace(",", "."))
    return -n if m.group(1) == "-" else n


def interpret_drapeau(etalonnage_type: str | None, valeur, cfg: dict) -> str:
    """Déduit norme/fragilité/pathologique/sévère depuis l'étalonnage + seuils config.

    Deux échelles de notes standard coexistent en orthophonie et ne sont PAS
    interchangeables : les batteries françaises (EXALANG, EVALEO…) cotent en
    moyenne 10 / ET 3, d'autres outils (Vineland…) en moyenne 100 / ET 15. Une
    note de 85 vaut −1 ET sur la seconde et sortirait « dans la norme » sur la
    première : l'échelle est donc choisie explicitement à la saisie, jamais
    devinée."""
    n = _parse_num(valeur)
    if n is None or not etalonnage_type:
        return ""
    s = cfg["seuils"]
    et = None
    if etalonnage_type == "ecart_type":
        et = n
    elif etalonnage_type == "note_standard":  # moyenne 10, ET 3
        et = (n - 10) / 3.0
    elif etalonnage_type == "note_standard_100":  # moyenne 100, ET 15
        et = (n - 100) / 15.0
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


# Bornes de plausibilité par type d'étalonnage. Elles ne corrigent jamais rien :
# une valeur hors bornes est signalée au praticien, qui seul peut trancher —
# même doctrine que la vérification des chiffres de la dictée. Sans elles, un
# percentile de -300 ressortait « déficit sévère » et une note de 85 saisie sur
# la mauvaise échelle ressortait « dans la norme », sans un mot.
BORNES_ETALONNAGE = {
    "percentile": (0.0, 100.0, "un percentile va de 0 à 100"),
    "ecart_type": (-6.0, 6.0, "un écart-type se situe entre -6 et +6"),
    "note_standard": (1.0, 19.0, "une note standard moy. 10 / ET 3 va de 1 à 19"),
    "note_standard_100": (40.0, 160.0,
                          "une note standard moy. 100 / ET 15 va de 40 à 160"),
}


def alerte_etalonnage(etalonnage_type: str | None, valeur) -> str:
    """Message d'alerte si la valeur sort des bornes de son échelle ('' sinon)."""
    bornes = BORNES_ETALONNAGE.get(etalonnage_type or "")
    if not bornes:
        return ""
    n = _parse_num(valeur)
    if n is None:
        return ""
    bas, haut, rappel = bornes
    if bas <= n <= haut:
        return ""
    return f"« {valeur} » sort des valeurs possibles ({rappel})"


def alertes_plausibilite(
    test_nom: str, resultats: list[dict], cfg: dict | None = None,
) -> list[str]:
    """Alertes de saisie pour une épreuve, prêtes à être affichées telles quelles.

    Avec ``cfg`` (relecture d'un brouillon), le drapeau enregistré est aussi
    confronté à celui que donnent aujourd'hui la valeur et les seuils : il est
    figé à la saisie, et le tableau du compte-rendu l'imprime tel quel. Deux
    causes d'écart, toutes deux invisibles sans cela — des seuils modifiés
    depuis, ou une valeur saisie avant que son signe moins ne soit reconnu
    (« −2,1 » classé « dans la norme » jusqu'à la 1.14.0)."""
    out = []
    for r in resultats:
        tete = test_nom + (f" — {r['sous_epreuve']}" if r.get("sous_epreuve") else "")
        msg = alerte_etalonnage(*etalonnage_effectif(r))
        if msg:
            out.append(
                f"{tete} : {msg}. Vérifiez l'échelle choisie et la valeur saisie — "
                "le drapeau en dépend."
            )
        if cfg is None:
            continue
        enregistre = r.get("drapeau_seuil")
        attendu = interpret_drapeau(*etalonnage_effectif(r), cfg)
        if attendu and enregistre in DRAPEAU_LIBELLE and attendu != enregistre:
            out.append(
                f"{tete} : le drapeau enregistré (« {DRAPEAU_LIBELLE[enregistre]} ») ne "
                f"correspond pas à la valeur saisie et à vos seuils "
                f"(« {DRAPEAU_LIBELLE[attendu]} »). Supprimez cette épreuve et "
                "saisissez-la de nouveau : le tableau du compte-rendu imprime le "
                "drapeau enregistré."
            )
    return out


def etalonnage_effectif(r: dict) -> tuple[str | None, str | None]:
    """(type, valeur) sur lesquels porte le drapeau.

    L'étalonnage explicite prime ; à défaut, un percentile ou une note standard
    saisis dans leur champ propre (API) valent étalonnage. Ces champs étaient
    écrits en base et jamais relus — ni pour le drapeau, ni à l'export : une
    illusion de saisie conservée (revue du 2026-08-11, 9.4)."""
    if r.get("etalonnage_valeur"):
        return r.get("etalonnage_type"), r.get("etalonnage_valeur")
    if r.get("percentile"):
        return "percentile", r.get("percentile")
    if r.get("note_standard"):
        return "note_standard", r.get("note_standard")
    if r.get("age_dev"):
        return "age_dev", r.get("age_dev")
    return None, None


_PERCENTILE_SAISI = re.compile(r"^\s*[Pp]?\s*(\d+(?:[.,]\d+)?)\s*(?:er|e|ème|eme|ᵉ)?\s*$")


def _valeur_texte(t: str | None, v) -> str:
    if t == "percentile":
        # collé à la valeur : « 25e percentile », pas « 25 e percentile ». Une
        # valeur saisie « 10e », « 10ème » ou « P10 » ne reçoit pas un second
        # suffixe (« 10ee percentile »), et le premier s'écrit « 1er ».
        m = _PERCENTILE_SAISI.match(str(v))
        if m:
            v = m.group(1)
        return f"{v}er percentile" if str(v) == "1" else f"{v}e percentile"
    return f"{v} {_ET_LBL.get(t, '')}".strip()


def etalonnage_texte(r: dict) -> str:
    """Étalonnage suivi de son unité (« -1,5 ET », « 25e percentile »), puis
    les compléments saisis à part (percentile, note standard, âge de
    développement) qui ne le répètent pas, séparés par « · ».

    Source unique de cette mise en forme : la phrase-type et le tableau des
    résultats de l'export doivent afficher la même unité, faute de quoi le
    praticien ne pourrait plus relire l'échelle sur laquelle il a coté."""
    t, v = etalonnage_effectif(r)
    parts = [_valeur_texte(t, v)] if v else []
    if r.get("percentile") and (t, str(v)) != ("percentile", str(r["percentile"])):
        parts.append(_valeur_texte("percentile", r["percentile"]))
    if r.get("note_standard") and (t, str(v)) != ("note_standard", str(r["note_standard"])):
        parts.append(_valeur_texte("note_standard", r["note_standard"]))
    if r.get("age_dev") and (t, str(v)) != ("age_dev", str(r["age_dev"])):
        parts.append(_valeur_texte("age_dev", r["age_dev"]))
    return " · ".join(parts)


def resultat_phrase(test_nom: str, r: dict) -> str:
    """Phrase-type de restitution d'un résultat (déterministe, sans LLM)."""
    tete = test_nom + (f" — {r['sous_epreuve']}" if r.get("sous_epreuve") else "") + " :"
    parts = []
    if r.get("score_brut"):
        parts.append(f"score {r['score_brut']}")
    etal = etalonnage_texte(r)
    if etal:
        parts.append(etal)
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
    """Enregistre une épreuve et ses résultats, drapeau de sévérité déduit.

    Les résultats ne sont plus recopiés en phrases dans la rubrique
    « épreuves » : à l'usage, ces lignes s'empilaient à la suite de la prose
    de l'IA et ressortaient telles quelles dans le .docx adressé au
    prescripteur. Ils sont désormais rendus comme un **tableau** à l'export
    (cf. `export.py`), ce qui les tient à leur place et laisse la rubrique au
    commentaire clinique. `resultat_phrase` sert toujours ce rendu."""
    eid = con.execute(
        "INSERT INTO epreuve(bilan_id, domaine, test_nom, version) VALUES(?,?,?,?)",
        (bilan_id, domaine, test_nom, version),
    ).lastrowid
    stored = []
    for r in resultats:
        r = {k: sans_controles(v) if isinstance(v, str) else v for k, v in r.items()}
        drap = r.get("drapeau_seuil") or interpret_drapeau(*etalonnage_effectif(r), cfg)
        con.execute(
            "INSERT INTO resultat(epreuve_id, sous_epreuve, score_brut, etalonnage_type, "
            "etalonnage_valeur, percentile, note_standard, age_dev, interpretation, drapeau_seuil) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (eid, r.get("sous_epreuve"), r.get("score_brut"), r.get("etalonnage_type"),
             r.get("etalonnage_valeur"), r.get("percentile"), r.get("note_standard"),
             r.get("age_dev"), r.get("interpretation"), drap),
        )
        stored.append({**r, "drapeau_seuil": drap})
    _contenu_modifie(con, bilan_id)  # le tableau des résultats change
    return {"id": eid, "test_nom": test_nom, "domaine": domaine,
            "version": version, "resultats": stored}
