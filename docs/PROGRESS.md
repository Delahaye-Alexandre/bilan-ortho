# Avancement — bilan-ortho

Plan validé : `~/.claude/plans/curious-exploring-squid.md`. Recherche : `docs/recherche-bilan-ortho.md`.
Cible : production complète, générique & configurable, Python/FastAPI local, dictée auto-adaptative.

## Phases

- [x] **Phase 0 — Fondations & sécurité** *(fait, testé)*
  - Base chiffrée SQLCipher (`app/db.py`) + index vectoriel sqlite-vec (dim 1024, bge-m3) dans la même base.
  - Schéma complet (patient, prescription, bilan, section, epreuve, resultat, diagnostic, projet, cotation, envoi, consentement, audit_log, bilan_reference, dictee, config, meta).
  - Couche config (`app/config.py`) : `DEFAULTS` + surcharges praticien (fusion profonde), 11 domaines.
  - Sécurité (`app/security.py`) : déverrouillage passphrase, connexion chiffrée unique + verrou, auto-verrouillage inactivité, journal d'audit, transaction().
  - API (`app/main.py`) : `/api/status`, `/api/unlock`, `/api/lock`, `/api/config` (GET/PUT), `/api/domaines` ; génération existante conservée.
  - UI : écran de déverrouillage (création du coffre au 1er lancement) gate l'app.
  - Docs : recherche, notice médico-légale, registre RGPD.
  - **Vérifié** : création coffre, 423 si verrouillé, unlock OK, 401 mauvaise passphrase, aucune fuite en clair sur disque.
- [x] **Phase 1 — Dictée vocale locale** *(fait, testé)*
  - `app/stt.py` : faster-whisper auto-adaptatif (`resolved()` → cpu/medium/int8 sur cette machine ; GPU seulement si VRAM ≥ 6 Go), cache modèle, `hotwords` (glossaire ortho), corrections déterministes, `vad_filter`, suppression du fichier audio temporaire.
  - `/api/transcribe` (upload multipart, `python-multipart`) + `/api/stt/info` ; audit sans contenu.
  - UI : panneau « Dictée vocale » (MediaRecorder → transcription locale ajoutée au texte).
  - **Vérifié** : pipeline direct + HTTP end-to-end transcrivent une vraie parole (`"this is a spoken dictation test."`), audio non conservé, GET→405.
  - Sur la machine d'Alexandre : le défaut télécharge `medium` (~1,5 Go) au 1er usage réel et transcrit en FR ; possibilité de pointer `stt.model` vers un modèle CT2 fine-tuné FR pour la qualité max.
- [x] **Phase 2 — Structuration IA + dialogue de clarification** *(fait, testé)*
  - `app/prompts.py` : prompt de structuration (JSON strict) + checklist de zones d'ombre (âge manquant, score sans étalonnage, test sans résultat, appréciation vague, diagnostic à étayer).
  - `app/llm.py` : `chat_json` (Ollama `/api/chat` format JSON) + `structure()` (routage dictée→rubriques + questions) avec parse tolérant, ne garde que des clés valides.
  - `app/bilan.py` : CRUD bilan + rubriques (tronc commun), `apply_updates` (statut propose_ia), `update_section`, liste.
  - `app/main.py` : `POST/GET /api/bilans`, `GET /api/bilans/{id}`, `POST /api/bilans/{id}/structure`, `PUT …/sections/{cle}`.
  - UI reconstruite : parcours nouveau bilan → dictée → « Structurer » → rubriques éditables avec badges (vide/à valider/validé) + panneau « Questions de l'assistant » (répondre = re-structuration ciblée) + copier le bilan.
  - **Vérifié** (Ollama qwen2.5:7b réel + HTTP) : routage correct, aucun score inventé, diagnostic reformulé en proposition, questions pertinentes, validation de rubrique persistée.
  - Limite : qualité de détection bornée par le modèle (qwen 7b) — modèle configurable dans l'UI.
- [x] **Phase 3 — Domaines, tests/scores, cotation, export** *(fait, testé)*
  - `app/catalogues.py` : par domaine, orientations de rédaction + catalogues de tests étalonnés (ELO, EXALANG, Alouette, TEDI-MATH, MT-86, GRBAS…). Injectés dans le prompt de structuration (l'IA reconnaît les tests) et proposés à la saisie.
  - `app/bilan.py` : saisie structurée des épreuves/résultats + `interpret_drapeau` (ET / percentile / note standard → norme/fragilité/pathologique/sévère depuis les seuils config) + phrases-types auto ajoutées à la rubrique « épreuves ».
  - `app/cotation.py` : cotation NGAP paramétrable (AMO simple 24 / complexe 34 / renouv. 30, valeur 2,60 €).
  - `app/export.py` : export **Word (.docx)** + Markdown + texte (python-docx).
  - `app/main.py` : `GET /api/catalogues/{domaine}`, `POST …/epreuves`, `POST …/cotation`, `GET …/export?format=docx|md|txt`.
  - UI : carte « Épreuves & scores » (saisie test + datalist par domaine + drapeau auto), barre d'actions (coter, export Word/Markdown, copier).
  - **Vérifié** (backend + HTTP) : interprétation d'étalonnage, cotation, épreuve→drapeau, export docx (zip valide) + md.
- [x] **Phase 4 — Base des bilans du praticien (import OCR + RAG style)** *(fait, testé 2026-07-04)*
  - `app/importer.py` : extraction texte (PDF natif via pypdf, PDF scanné via OCRmyPDF/Tesseract si installés, texte brut), découpage par rubriques (en-têtes du tronc commun), ingestion.
  - `app/rag.py` : embeddings Ollama (`nomic-embed-text` défaut, `bge-m3` en option), index sqlite-vec **dans la base chiffrée**, table recréée si le modèle d'embeddings change (dimension), récupération top-k filtrée domaine/section.
  - `app/main.py` : `POST/GET/DELETE /api/references` ; injection des extraits de style dans la structuration (best-effort, k = `style.few_shot_k`).
  - UI : panneau « Mes bilans de référence » (import fichier + domaine, liste, suppression).
  - `data/reference/` : 4 bilans **fictifs** d'amorce (langage écrit, langage oral, voix, neuro acquise) + README.
  - **Vérifié** (HTTP + base réelle) : import txt (7 extraits) et PDF natif (4 extraits), 11 vecteurs = 11 références, retrieve pertinent avec filtres domaine/section étanches, suppression propre (référence + vecteur), structuration réelle (qwen 7b, 53 s) avec style injecté et questions conformes à la checklist, audit journalisé.
- [x] **Phase 5 — Configurabilité complète + finitions UX** *(fait, testé 2026-07-04)*
  - UI : écran **⚙️ Paramètres** complet (LLM, dictée : device/modèle/beam/VAD/langue/vocabulaire/corrections, style : k/vouvoiement/détail, embeddings, seuils ET, cotation NGAP, RGPD : verrouillage/conservation) + éditeur **Avancé (JSON)** pour la **trame**, les **catalogues de tests** et le **prompt de structuration** (`{cles}` substitué par replace — accolades littérales OK) + **❓ Aide** (parcours pas à pas, RGPD).
  - `DELETE /api/config` (réinitialisation) + `GET /api/config/overrides` + `ConfigStore.reset()`.
  - Réglages désormais **appliqués** : `style.niveau_detail`/`style.vouvoiement` injectés dans le prompt ; `rgpd.conservation_jours` purge les bilans inactifs au déverrouillage (cascade + audit) ; trame/catalogues/prompt surchargés par la config (validation défensive, repli tronc commun).
  - **Cycle de vie** : `PUT /api/bilans/{id}/statut` (brouillon → validé → envoyé ; envoi tracé dans `envoi` avec destinataire + audit) + boutons UI.
  - Clés mortes retirées (`rgpd.audio_purge_apres_validation`, `ui.theme`) : l'audio est **toujours** purgé (stt.py), dit honnêtement dans l'UI.
  - **Tests automatisés** : `tests/` — 49 tests pytest 100 % hors ligne (LLM/embeddings mockés, base chiffrée temporaire) : sécurité (passphrase, 423/401, auto-verrouillage, purge), config (fusion/reset/overrides), CRUD bilan, trame configurable, statut/envoi, drapeaux d'étalonnage, cotation, catalogues surchargés, import/sectionnage, RAG, API complète, exports. `pytest tests/`.
  - Docs : README réécrit (guide utilisateur complet), `requirements.txt` nettoyé, version 1.0.0.
  - **Vérifié** : 49/49 tests verts ; serveur relancé — page, cycle config PUT/DELETE, statut valide/envoyé et overrides OK en HTTP réel ; syntaxe JS validée (bun), tous les ids DOM présents.
  - Non retenu (assumé) : export PDF direct (Word + impression navigateur couvrent le besoin) ; édition des domaines actifs ; UI dédiée (non-JSON) pour trame/catalogues/prompts.
- [x] **Post-v1.0 (2026-07-05) — Patients & sauvegardes (v1.1.0)** *(fait, testé)*
  - `app/patient.py` : fiche minimale (nom, prénom, date de naissance, sexe, notes), CRUD `GET/POST/PUT/DELETE /api/patients`, **effacement RGPD** en cascade (bilans, sections, épreuves, dictées… suivent les FK), `age_texte`/`date_fr`.
  - Bilans **rattachés** : sélecteur patient + modal 👤 dans l'UI, nom dans la liste des bilans, identité + âge à la date du bilan sur les exports, **âge/sexe injectés dans le prompt de structuration** (minimisation : jamais le nom) → l'IA ne redemande plus l'âge.
  - `app/sauvegarde.py` : copie cohérente **chiffrée** du coffre (`VACUUM INTO`, même passphrase), dossier configurable, rotation (rétention), **auto au déverrouillage** si plus ancienne que `sauvegarde.auto_jours` (défaut 7, best-effort, ne bloque jamais l'unlock), `POST /api/sauvegarde` + `GET /api/sauvegardes`, bouton + réglages dans ⚙️ Paramètres, procédure de restauration documentée (README).
  - **Vérifié** : 60/60 tests (dont chiffrement de la copie, rotation, cascade RGPD, âge veille d'anniversaire) ; live : export « Patient : ESSAI Zoé, né(e) le 01/02/2019 (7 ans et 5 mois à la date du bilan) », sauvegarde auto au déverrouillage + manuelle, copie sans aucun octet en clair.

- [x] **Post-v1.0 (2026-07-05) — Lanceur Windows `BilanOrtho.exe`** *(fait, testé)*
  - `packaging/windows/BilanOrtho.cs` : lanceur C# compilé par le `csc.exe` intégré à Windows (`packaging/windows/build.sh`, icône générée via Pillow, zéro dépendance). Double-clic → si le serveur répond : ouvre le navigateur ; sinon : lance `scripts/start-serveur.sh` dans WSL (caché), attend jusqu'à 60 s, ouvre le navigateur ; message d'erreur avec chemin du journal en cas d'échec.
  - `scripts/start-serveur.sh` : idempotent (teste les ports avant de lancer Ollama/uvicorn — plus jamais de « address already in use »), journaux dans `~/.local/share/bilan-ortho/`.
  - **Vérifié** : exe copié sur le Bureau et exécuté depuis Windows — démarrage à froid OK (serveur up, 1 seul process), relance avec serveur déjà up → simple ouverture du navigateur, aucun doublon.
  - Distribution à d'autres orthophonistes (build natif Windows + installeur Ollama/Tesseract) : chantier séparé, non commencé (choix d'Alexandre : « mon PC d'abord »).

- [~] **Chantier distribution (2026-07-05, plan validé `piped-pondering-hoare`)** — en cours
  - [x] Phase A : dépôt GitHub **privé** `Delahaye-Alexandre/bilan-ortho`, tag v1.1.0.
  - [x] Phase B : portabilité Windows natif — `sqlcipher3` officiel (roues win_amd64, même format de coffre) via marqueurs de plateforme, `data_dir` → `%LOCALAPPDATA%`, Tesseract Windows détecté, `lanceur.py` (single-instance, ports 8000-8010).
  - [x] Phase C : premier lancement guidé — `app/systeme.py` (RAM, proposition **qwen3.5:9b** ≥16 Go / **qwen3.5:4b** 8-16 Go, recherche 07/2026), `GET /api/installation` + `POST /api/installation/pull` (NDJSON), écran UI avec progression, bascule du modèle après déverrouillage. OCR refactoré sur l'API Python ocrmypdf (compatible app compilée).
  - [x] Phase E (jalon 1) : **CI verte sur windows-latest + ubuntu-latest** (68 tests) — SQLCipher Windows validé en vrai.
  - [x] Phase D : spec PyInstaller onedir (DLL natives collectées), installeur Inno (par utilisateur, données préservées), job CI build + fumage du binaire + Release draft sur tag.
  - [x] Phase F (partie automatisable) : installeur du build CI **testé en réel sur le Windows d'Alexandre** — installation silencieuse OK, app native démarrée, coffre chiffré natif créé (`%LOCALAPPDATA%\bilan-ortho`, nettoyé après test), bilan + export docx OK, RAM détectée 31,7 Gio → proposition qwen3.5:9b. Découverte : un **Ollama Windows sans modèles** tourne en plus de l'Ollama WSL → l'app native passera par l'écran guidé pour tirer ses modèles côté Windows (comportement testeuse nominal). `docs/guide-testeuse.md` rédigé et attaché à la release.
  - **Release v1.2.0 (draft, privée)** : `BilanOrtho-Setup-1.2.0.exe` (70 Mo) + guide — https://github.com/Delahaye-Alexandre/bilan-ortho/releases . Reste humain : passe manuelle d'Alexandre (double-clic, écran guidé, pull des modèles Windows), envoi du lien aux testeuses, retours.
  - Note machine d'Alexandre : l'app native Windows verra l'Ollama de WSL via localhost (port forwarding) et utilisera un coffre séparé (`%LOCALAPPDATA%\bilan-ortho`) — les données WSL ne bougent pas. Arrêter le serveur WSL avant de tester le natif (sinon le lanceur s'attache à l'instance WSL existante).

## Environnement (machine d'Alexandre)
- Python 3.12.3, venv `.venv`. Ollama présent : `qwen2.5:7b-instruct-q4_K_M` (défaut LLM) + `glm-5.2:cloud` (⚠️ jamais sur données patient).
- GPU RTX 3050 Ti **4 Go VRAM** (partagé avec Ollama) → STT lean CPU/distillé.
- OCR **installé et vérifié** (2026-07-04) : tesseract 5.3.4 + `fra`, ghostscript, ocrmypdf 17.8.0 (pip, venv). Import d'un PDF scanné testé de bout en bout via l'API (7,5 s). Correctif au passage : `importer._ocr_pdf` invoque `python -m ocrmypdf` (indépendant du PATH) au lieu du binaire.

## Lancer
`./run.sh` → http://localhost:8000 (bind 127.0.0.1). Données : `~/.local/share/bilan-ortho/` (surchargeable via `BILAN_ORTHO_DATA_DIR`).
