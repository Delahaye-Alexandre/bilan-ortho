"""RAG local « style du praticien » : embeddings (Ollama) + index sqlite-vec.

Les bilans de référence du praticien sont vectorisés et stockés dans la même
base chiffrée. Au moment de rédiger, on récupère les extraits les plus proches
pour inspirer le style — sans aucun envoi réseau (Ollama local).
"""
from __future__ import annotations

import httpx
import sqlite_vec


class EmbeddingUnavailable(RuntimeError):
    """Modèle d'embeddings absent ou Ollama injoignable."""


def _dicts(cur) -> list[dict]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


async def embed(text: str, cfg: dict) -> list[float]:
    """Calcule l'embedding d'un texte via Ollama.

    Asynchrone : l'appel réseau (potentiellement long) rend la main à
    l'event loop — il doit être fait HORS de ``security.transaction()``
    pour ne jamais geler le serveur sous le verrou global (audit C3)."""
    e = cfg["embeddings"]
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{e['host']}/api/embeddings",
                json={"model": e["model"], "prompt": text},
            )
            r.raise_for_status()
            emb = r.json().get("embedding")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise EmbeddingUnavailable(
                f"Modèle d'embeddings « {e['model']} » absent. "
                f"Faites : ollama pull {e['model']}"
            ) from exc
        raise EmbeddingUnavailable(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise EmbeddingUnavailable("Ollama injoignable pour les embeddings.") from exc
    if not emb:
        raise EmbeddingUnavailable("Réponse d'embeddings vide.")
    return emb


def _ensure_table(con, dim: int) -> None:
    """Crée reference_embedding à la bonne dimension (recrée si le modèle change)."""
    row = con.execute("SELECT value FROM meta WHERE key='embed_dim'").fetchone()
    cur_dim = int(row[0]) if row else None
    if cur_dim == dim:
        return
    if cur_dim is not None:
        # Changement de modèle d'embeddings : les vecteurs existants sont invalidés.
        con.execute("DROP TABLE IF EXISTS reference_embedding")
        con.execute("DELETE FROM bilan_reference")
    con.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS reference_embedding "
        f"USING vec0(embedding float[{dim}])"
    )
    con.execute(
        "INSERT INTO meta(key,value) VALUES('embed_dim',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(dim),),
    )


def add_reference(
    con, praticien_id, source: str, domaine: str, section_cle: str,
    titre: str, texte: str, emb: list[float],
) -> int:
    """Insère une référence + son vecteur. ``emb`` est calculé au préalable
    (via :func:`embed`), hors transaction : ici, uniquement de la base."""
    _ensure_table(con, len(emb))
    rid = con.execute(
        "INSERT INTO bilan_reference(praticien_id, source, domaine, section_cle, titre, texte) "
        "VALUES(?,?,?,?,?,?)",
        (praticien_id, source, domaine, section_cle, titre, texte),
    ).lastrowid
    con.execute(
        "INSERT INTO reference_embedding(rowid, embedding) VALUES(?,?)",
        (rid, sqlite_vec.serialize_float32(emb)),
    )
    return rid


def _table_exists(con) -> bool:
    return con.execute(
        "SELECT count(*) FROM sqlite_master WHERE name='reference_embedding'"
    ).fetchone()[0] > 0


def retrieve(
    con, emb: list[float] | None, domaine: str | None = None,
    section_cle: str | None = None, k: int = 4,
) -> list[dict]:
    """Extraits de référence les plus proches du vecteur ``emb`` (filtrés par
    section/domaine). ``emb`` est calculé au préalable, hors transaction."""
    if not emb or not _table_exists(con):
        return []
    rows = con.execute(
        "SELECT rowid, distance FROM reference_embedding "
        "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (sqlite_vec.serialize_float32(emb), max(k * 5, k)),
    ).fetchall()
    ids = [r[0] for r in rows]
    if not ids:
        return []
    ph = ",".join("?" * len(ids))
    refs = {r["id"]: r for r in _dicts(
        con.execute(f"SELECT * FROM bilan_reference WHERE id IN ({ph})", ids)
    )}
    out = []
    for rid in ids:
        ref = refs.get(rid)
        if not ref:
            continue
        if section_cle and ref["section_cle"] not in (section_cle, "global"):
            continue
        if domaine and ref.get("domaine") and ref["domaine"] != domaine:
            continue
        out.append(ref)
        if len(out) >= k:
            break
    return out


def liste(con) -> list[dict]:
    return _dicts(con.execute(
        "SELECT id, source, domaine, section_cle, titre, length(texte) AS taille, created_at "
        "FROM bilan_reference ORDER BY id DESC"
    ))


def delete(con, ref_id: int) -> None:
    con.execute("DELETE FROM bilan_reference WHERE id=?", (ref_id,))
    if _table_exists(con):
        con.execute("DELETE FROM reference_embedding WHERE rowid=?", (ref_id,))
