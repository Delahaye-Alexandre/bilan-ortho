"""Transcription vocale locale (faster-whisper), auto-adaptative au matériel.

Aucune donnée ne quitte la machine : l'audio est transcrit en local puis le
fichier temporaire est immédiatement supprimé (minimisation RGPD).

Politique « auto » :
- **device** : GPU seulement si CUDA présent ET VRAM totale ≥ 6 Go (sinon CPU) —
  sur une machine où Ollama occupe déjà un petit GPU, on reste sur CPU.
- **model** : `large-v3` sur GPU, `medium` sur CPU (qualité FR ; configurable).
- Pour la meilleure qualité FR, pointer `stt.model` vers un modèle CTranslate2
  fine-tuné FR (ex. conversion de `bofenghuang/whisper-large-v3-french`).
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading

import av

_lock = threading.Lock()
_cache: dict = {"model": None, "spec": None}


class DicteeTropLongue(ValueError):
    """Enregistrement plus long que `rgpd.dictee_max_minutes` : la borne ne
    vivait que dans le navigateur (arrêt automatique du micro), un envoi
    direct à l'API l'ignorait."""

    def __init__(self, duree_s: float, max_minutes: float):
        self.duree_s, self.max_minutes = duree_s, max_minutes
        super().__init__(
            f"Dictée trop longue ({duree_s / 60:.0f} min) : la limite est de "
            f"{max_minutes:g} min (⚙️ Paramètres → Sécurité et sauvegardes). "
            "Dictez en plusieurs fois."
        )


class AudioIllisible(ValueError):
    """L'enregistrement reçu n'est pas décodable (fichier tronqué, format
    inattendu) : c'est un problème du fichier envoyé, pas du modèle."""


class STTUnavailable(RuntimeError):
    """faster-whisper n'est pas installé."""


def _cuda_device_count() -> int:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def _vram_total_mib() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip().splitlines()
        return int(out[0].strip()) if out else None
    except Exception:
        return None


_MATERIEL: dict | None = None
_MATERIEL_LOCK = threading.Lock()


def _materiel() -> dict:
    """GPU utilisable ? Détecté une fois par processus : l'import de ctranslate2
    et l'appel à nvidia-smi coûtent jusqu'à plusieurs secondes sous Windows, et
    cette détection était refaite à chaque écran d'installation et à chaque
    « Dictée : … » — le matériel, lui, ne change pas en cours d'exécution."""
    global _MATERIEL
    with _MATERIEL_LOCK:
        if _MATERIEL is None:
            _MATERIEL = {"cuda": _cuda_device_count() > 0, "vram_mib": _vram_total_mib() or 0}
        return _MATERIEL


def resolved(cfg: dict) -> dict:
    """Résout (sans charger le modèle) le device/compute_type/model effectifs."""
    stt = cfg["stt"]
    device = stt.get("device", "auto")
    if device == "auto":
        m = _materiel()
        device = "cuda" if (m["cuda"] and m["vram_mib"] >= 6000) else "cpu"

    compute = stt.get("compute_type", "auto")
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    model = stt.get("model", "auto")
    if not model or model == "auto":
        model = "large-v3" if device == "cuda" else "medium"

    return {"device": device, "compute_type": compute, "model": model}


# Tailles approximatives des modèles CTranslate2 int8/float16 distribués par
# Systran, pour l'écran d'installation.
TAILLES_GO = {"tiny": 0.08, "base": 0.15, "small": 0.5, "medium": 1.5, "large-v3": 3.1, "large": 3.1}


def taille_estimee_go(modele: str) -> float:
    return TAILLES_GO.get((modele or "").split("/")[-1].replace("faster-whisper-", ""), 1.5)


def modele_present(cfg: dict) -> bool:
    """Le modèle de dictée résolu est-il déjà dans le cache local ? Sans réseau.

    Jusqu'ici, Whisper (~1,5 Go) se téléchargeait au premier « Arrêter » —
    après que la personne avait parlé — hors de tout écran d'installation
    (revue du 2026-08-11, 6.3)."""
    spec = resolved(cfg)
    try:
        from faster_whisper.utils import download_model

        download_model(spec["model"], local_files_only=True)
        return True
    except Exception:
        return False


_telechargement: dict = {"etat": "inactif", "message": "", "modele": ""}
_tl_lock = threading.Lock()


def etat_telechargement() -> dict:
    with _tl_lock:
        return dict(_telechargement)


def telecharger_en_arriere_plan(cfg: dict) -> dict:
    """Télécharge (et charge) le modèle de dictée dans un thread démon, une
    seule fois à la fois. Hugging Face ne donne pas de progression exploitable
    ici : l'écran d'installation suit l'état (en_cours / termine / erreur)."""
    spec = resolved(cfg)
    with _tl_lock:
        if _telechargement["etat"] == "en_cours":
            return dict(_telechargement)
        _telechargement.update(etat="en_cours", message="", modele=spec["model"])

    def travail():
        try:
            _get_model(spec)
            with _tl_lock:
                _telechargement.update(etat="termine", message="")
        except Exception as exc:
            with _tl_lock:
                _telechargement.update(etat="erreur", message=str(exc)[:300])

    threading.Thread(target=travail, daemon=True, name="whisper-telechargement").start()
    return dict(_telechargement)


def _get_model(spec: dict):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover
        raise STTUnavailable(
            "faster-whisper n'est pas installé (pip install faster-whisper)."
        ) from exc

    with _lock:
        if _cache["spec"] != spec or _cache["model"] is None:
            _cache["model"] = WhisperModel(
                spec["model"], device=spec["device"], compute_type=spec["compute_type"]
            )
            _cache["spec"] = spec
        return _cache["model"]


# Corrections appliquées après transcription. Une correction remplace le mot
# entier, tel qu'il est écrit, majuscule ou non : « ortofonie => orthophonie ».
# L'expression régulière (comportement d'origine, sensible à la casse) se garde
# avec le préfixe « re: » — sans ce garde-fou, « N.E.E.L » remplaçait n'importe
# quels caractères et « ortho » transformait « orthophoniste ».
PREFIXE_REGEX = "re:"


def _apply_corrections(text: str, corrections: dict) -> str:
    for motif, repl in (corrections or {}).items():
        motif = str(motif)
        if motif.startswith(PREFIXE_REGEX):
            try:
                text = re.sub(motif[len(PREFIXE_REGEX):], repl, text)
            except re.error:
                # Corrections mal formées : on ignore plutôt que de planter la dictée.
                continue
        elif motif.strip():
            # (?<!\w) / (?!\w) plutôt que \b : « N.E.E.L » finit par un signe,
            # où \b ne marque pas de frontière. Remplacement littéral (lambda) :
            # un « \ » dans le texte voulu n'est pas interprété.
            text = re.sub(
                rf"(?<!\w){re.escape(motif.strip())}(?!\w)",
                lambda _m, r=repl: r, text, flags=re.IGNORECASE,
            )
    return text


# Marge sur la borne de durée : le navigateur arrête le micro à la limite,
# l'enregistrement qui en sort la dépasse de quelques secondes.
_TOLERANCE_DUREE_S = 10.0


def _duree_audio(chemin: str) -> float | None:
    """Durée annoncée par le conteneur (secondes), ou None si elle n'y est
    pas — un WebM de MediaRecorder n'en porte souvent aucune — ou si le
    fichier n'est pas décodable (le modèle le dira mieux)."""
    try:
        with av.open(chemin) as conteneur:
            if conteneur.duration:
                return float(conteneur.duration / av.time_base)  # av.time_base = 1 000 000
    except Exception:
        return None
    return None


def _verifier_duree(duree_s: float | None, cfg: dict) -> None:
    max_minutes = float(((cfg.get("rgpd") or {}).get("dictee_max_minutes")) or 0)
    if max_minutes > 0 and duree_s and duree_s > max_minutes * 60 + _TOLERANCE_DUREE_S:
        raise DicteeTropLongue(duree_s, max_minutes)


def transcribe(audio_bytes: bytes, filename: str, cfg: dict) -> dict:
    """Transcrit un audio (bytes) et supprime le fichier temporaire ensuite.

    La borne `rgpd.dictee_max_minutes` est appliquée ici aussi : avant la
    transcription quand le conteneur annonce sa durée, après sinon (la
    durée mesurée par le modèle) — le texte d'une dictée trop longue n'est
    jamais rendu."""
    stt = cfg["stt"]
    spec = resolved(cfg)
    model = _get_model(spec)

    hotwords = ", ".join(stt.get("hotwords", [])) or None
    suffix = os.path.splitext(filename or "")[1] or ".webm"

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(audio_bytes)
        tmp.flush()
        tmp.close()
        _verifier_duree(_duree_audio(tmp.name), cfg)
        try:
            segments, info = model.transcribe(
                tmp.name,
                language=stt.get("language", "fr"),
                vad_filter=stt.get("vad", True),
                beam_size=int(stt.get("beam_size", 5)),
                hotwords=hotwords,
            )
        except av.error.InvalidDataError as exc:
            # Le décodage (PyAV/ffmpeg) refuse le fichier lui-même : rien à
            # voir avec l'installation du modèle, le message doit le dire.
            raise AudioIllisible(str(exc)) from exc
        text = "".join(seg.text for seg in segments).strip()
        _verifier_duree(float(getattr(info, "duration", 0.0) or 0.0), cfg)
        text = _apply_corrections(text, stt.get("corrections", {}))
        return {
            "text": text,
            "language": getattr(info, "language", stt.get("language", "fr")),
            "duration": round(getattr(info, "duration", 0.0), 2),
            "model": spec["model"],
            "device": spec["device"],
        }
    finally:
        # Purge de l'audio brut (minimisation).
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
