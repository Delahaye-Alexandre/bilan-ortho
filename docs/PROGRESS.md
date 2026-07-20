# Avancement — bilan-ortho

Recherche : `docs/recherche-bilan-ortho.md`.
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
  - Possibilité de pointer `stt.model` vers un modèle CT2 fine-tuné FR pour la qualité max.
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

- [~] **Chantier distribution (2026-07-05)** — en cours
  - [x] Phase A : dépôt GitHub **privé** `Delahaye-Alexandre/bilan-ortho`, tag v1.1.0.
  - [x] Phase B : portabilité Windows natif — `sqlcipher3` officiel (roues win_amd64, même format de coffre) via marqueurs de plateforme, `data_dir` → `%LOCALAPPDATA%`, Tesseract Windows détecté, `lanceur.py` (single-instance, ports 8000-8010).
  - [x] Phase C : premier lancement guidé — `app/systeme.py` (RAM, proposition **qwen3.5:9b** ≥16 Go / **qwen3.5:4b** 8-16 Go, recherche 07/2026), `GET /api/installation` + `POST /api/installation/pull` (NDJSON), écran UI avec progression, bascule du modèle après déverrouillage. OCR refactoré sur l'API Python ocrmypdf (compatible app compilée).
  - [x] Phase E (jalon 1) : **CI verte sur windows-latest + ubuntu-latest** (68 tests) — SQLCipher Windows validé en vrai.
  - [x] Phase D : spec PyInstaller onedir (DLL natives collectées), installeur Inno (par utilisateur, données préservées), job CI build + fumage du binaire + Release draft sur tag.
  - [x] Phase F (partie automatisable) : installeur du build CI **testé en réel sur le Windows d'Alexandre** — installation silencieuse OK, app native démarrée, coffre chiffré natif créé (`%LOCALAPPDATA%\bilan-ortho`, nettoyé après test), bilan + export docx OK, RAM détectée 31,7 Gio → proposition qwen3.5:9b. Découverte : un **Ollama Windows sans modèles** tourne en plus de l'Ollama WSL → l'app native passera par l'écran guidé pour tirer ses modèles côté Windows (comportement nominal attendu lors des tests). `docs/guide-test.md` (guide de test) rédigé et attaché à la release.
  - **Release v1.2.0 (draft, privée)** : `BilanOrtho-Setup-1.2.0.exe` (70 Mo) + guide — https://github.com/Delahaye-Alexandre/bilan-ortho/releases . Reste humain : passe manuelle (double-clic, écran guidé, pull des modèles Windows), envoi du lien aux personnes qui testent, retours.

- [x] **v1.2.1 (2026-07-05) — Fenêtre d'app dédiée + installeur tout-en-un** *(fait, release draft)*
  - Fenêtre d'application dédiée (mode `--app` d'Edge/Chrome, 1280×860, favicon SVG) au lieu d'un onglet navigateur — `lanceur.py` + lanceur C# WSL, repli navigateur classique si absent.
  - Installeur Inno **tout-en-un** : si Ollama est absent, son installeur officiel (~1 Go) est téléchargé (DownloadPage) puis exécuté en silencieux, et `ollama app` est démarré ; hors ligne, l'installation continue et l'écran guidé de l'app prend le relais.
  - **Release v1.2.1 (draft, privée)** : `BilanOrtho-Setup-1.2.1.exe` + guide de test (md + html). **Non envoyée** — remplacée par la v1.3.0 : son écran guidé propose qwen3.5 sans le correctif `think`, la personne qui teste subirait des minutes d'attente à chaque structuration.

- [x] **v1.3.0 (2026-07-11) — Correctifs issus des tests réels avec qwen3.5** *(fait, testé)*
  - `app/llm.py` : `"think": false` sur `/api/chat` — les modèles à raisonnement (qwen3.5) partaient en minutes de « réflexion » CPU avant de produire le JSON ; repli automatique sans le champ si un vieil Ollama répond 400.
  - `app/prompts.py` : les extraits de style injectés concernent **d'autres patients** — interdiction explicite d'y faire référence dans les textes ou questions (leurs tests/scores n'existent pas dans le dossier courant).
  - Version unique `__version__` dans `app/__init__.py` (rappel dans la docstring : bumper + tag à chaque release), affichée dans l'en-tête de l'UI et retournée par `/api/status`.
  - UX : « Analyse en cours… (jusqu'à 2-3 min selon la machine) » pendant la structuration.
  - **Vérifié** : 68/68 tests pytest ; E2E réel contre Ollama WSL 0.30.10 — qwen3.5:4b rend son JSON en 27 s (contre plusieurs minutes avant), qwen2.5:7b par défaut inchangé (HTTP 200 avec `think:false`, le repli 400 reste une sécurité pour les vieux Ollama).
  - Reste humain : passe rapide sur l'installeur 1.3.0, envoi du lien Release aux personnes qui testent, retours.

- [x] **Post-v1.3.0 (2026-07-11) — Panneau questions fiabilisé (une à une + envoi groupé)** *(fait, testé)*
  - Bug signalé par Alexandre : répondre à une question effaçait les réponses en cours de saisie des autres. Causes : re-rendu `innerHTML` intégral (brouillons perdus), cartes identifiées par position (indices périmés → mauvaise question supprimée), retrait de la question AVANT l'appel LLM (perdue en cas d'erreur), réponse envoyée sans sa question (routage hasardeux).
  - Correctif (`app/static/index.html` seul, aucune API touchée) : id stable par question, retrait après succès uniquement, brouillons sauvegardés/restaurés à chaque re-rendu, réponse contextualisée (« À la question “…” : … »), boutons désactivés pendant l'analyse (champs toujours éditables), dédoublonnage des questions reposées par l'IA, bouton « Envoyer les N réponses » dès 2 champs remplis (un seul passage IA pour plusieurs réponses).
  - **Vérifié** : test fonctionnel happy-dom sur la vraie page (19 scénarios : brouillons préservés, seule la question répondue retirée, erreur 500 sans perte, envoi groupé en un appel, boutons en vol) + 68 tests pytest + validé en réel par Alexandre.
  - **Release v1.3.1 (draft, privée)** taguée avec ce correctif — c'est elle qu'il faut envoyer aux personnes qui testent (le panneau questions est au cœur de leur parcours), pas la v1.3.0.

- [x] **v1.4.0 (2026-07-13, taguée 2026-07-16) — Mémoire du dialogue de clarification + panneau questions enrichi** *(fait, testé)*
  - Problème : l'IA reposait les mêmes questions à chaque dictée car elle ne voyait ni le contenu déjà rédigé ni l'historique du dialogue.
  - Backend : l'endpoint de structuration accepte des réponses **sans dictée** (payload structuré : `transcription`, `reponses` [{question, reponse, section}], `questions_en_attente/ecartees/repondues` ; 400 seulement si le tour est vide) ; le prompt reçoit le **contenu réel des rubriques** (tronqué à 1500 car./rubrique) + les 3 listes de questions avec interdiction de reposer (à l'identique comme reformulé) ; `num_ctx: 8192` par défaut (sinon Ollama tronque silencieusement à ~4k — passer à 16384 via la config si bilans très remplis).
  - Front : chrono sur « Analyse en cours… », bouton ✕ pour écarter une question, micro de dictée par question. Changement de sémantique assumé : les questions ouvertes **persistent après une nouvelle dictée** (avant : panneau remplacé) ; maps écartées/répondues par bilan, filtre de sûreté si l'IA repose quand même.
  - **Vérifié** : 70 tests pytest + 40 scénarios UI (`bun tests/ui/test_questions_ui.mjs`, happy-dom sur la vraie page — suite désormais versionnée dans le repo) + test réel puis go d'Alexandre le 13/07.

- [x] **v1.4.1 (2026-07-16) — Dictée native réparée + installeur robuste + vocabulaire neutre** *(correctifs issus de la passe manuelle d'Alexandre sur l'installeur v1.4.0)*
  - **Dictée cassée dans TOUTES les builds natives depuis la v1.2.0** (découvert à la première vraie dictée native) : le spec PyInstaller collectait le code de `faster_whisper` mais pas ses données — `assets/silero_vad_v6.onnx` manquait, et le VAD est actif par défaut (`stt.vad: true`) → `ONNXRuntimeError NO_SUCHFILE` à chaque transcription. Correctif : `collect_data_files("faster_whisper")` dans le spec + **garde-fou CI** (étape qui échoue si `silero_vad*.onnx` est absent du build — le test de fumée ne dicte pas, il ne pouvait pas le voir).
  - **Installeur** : `CloseApplications=force` + `taskkill /F /IM BilanOrtho.exe` dans `PrepareToInstall` — l'app est un processus sans fenêtre, le gestionnaire de redémarrage ne savait pas la fermer et la mise à jour affichait « Choisissez une action » (vécu par Alexandre en installant la 1.4.0 par-dessus une instance résiduelle).
  - **Vocabulaire neutre** (demande d'Alexandre) : `guide-testeuse.md` → `guide-test.md`, plus aucune désignation genrée dans le dépôt (README, CI, installeur, guide) ; assets et notes des releases mis à jour.
  - Non testable hors Windows : la collecte du spec et l'installeur sont validés par la CI (garde-fou VAD + fumée) puis par la passe manuelle.

- [x] **Post-v1.4.1 (2026-07-17) — Remédiation complète de l'audit** *(fait, testé — voir `docs/audit-2026-07-17.md`)*
  - **Lot 1 frontend** : wrapper `api()` (vérif. réponse, 423 → écran de verrouillage, erreurs en français), rubriques modifiées préservées au re-rendu (C2), garde anti-course et analyse unique dans `structure()`, anti double-clic, `beforeunload`. Test UI dédié (20 scénarios).
  - **Lot 2 sécurité** : `TrustedHostMiddleware` anti DNS rebinding (C1), surcharges de config validées Pydantic (C5), hôtes LLM/embeddings contraints en loopback (RGPD), passphrase ≥ 12 caractères à la création.
  - **Lot 3 fiabilité** : `embed()` asynchrone hors verrou (C3), timeout LLM borné, unlock/sauvegarde en threadpool, `enforce_inactivity` sous verrou, `updated_at` sur édition de rubrique (anti-purge RGPD), 423 explicites.
  - **Lot 4 intégrité** : import `.docx` réel + rejet des binaires, pagination des bilans.
  - **Lot 5 packaging** : purge `_internal` à la mise à jour, taskkill à la désinstallation, Ollama épinglé + SHA-256, garde-fou de version, fumée dictée sur binaire gelé.
  - **Lot 6 outillage** : ruff + job lint, tests UI en CI, `requirements.lock`, matrice Python 3.11-3.13.
  - **Lot 7 nettoyage** : endpoints legacy supprimés (`/api/generate`, `/api/sections` ; `/api/models` conservé pour l'UI mais verrouillé), `_dicts` factorisé, seuils percentile configurables, badges sévère/pathologique distincts, rotation de `serveur.log`, migrations de schéma (`PRAGMA user_version`), docs à jour.
  - **Lot 8 — les 3 constats absents du plan par lots de l'audit** : éditeur « Avancé » branché sur `/api/config/overrides` (les défauts ne sont plus figés en surcharges — les mises à jour atteignent de nouveau l'utilisateur) ; accessibilité (listes navigables au clavier, ✕ = vrais boutons Entrée/Espace, Échap ferme les modales + focus à l'ouverture, labels associés, `role="status"` sur les zones de statut) ; dépendances OCR installées en CI Linux + `pytest -rs` (plus de test sauté en silence).

- [x] **Post-v1.5.0 (2026-07-18) — Préparation de la publication open source** *(fait — documentation seule, aucun code touché)*
  - `LICENSE` : AGPL v3, texte officiel intégral.
  - `SECURITY.md` : signalement privé (mail, puis GitHub Security Advisories une fois le dépôt public), seule la dernière release supportée, correctif visé sous 30 jours pour les vulnérabilités critiques, périmètre et modèle de menace explicites (100 % local ; poste compromis et passphrase oubliée assumés hors périmètre).
  - `docs/charte-engagements.md` : 6 engagements publics adossés au fonctionnement réel (données locales, aucune IA entraînée sur les données, l'IA propose / le praticien signe, gratuité garantie par l'AGPL, limites documentées, chemin gratuit pérenne).
  - `docs/conformite/` : auto-évaluation AI Act (conclusion : pas un système d'IA à haut risque — hors annexe III, subsidiairement dérogation art. 6 §3) + déclaration de finalité MDR (pas un dispositif médical, argumentaire MDCG 2019-11). Les deux marquées « projet de document — à faire relire par un juriste avant publication ».
  - README : section « Licence & engagements » ; le dépôt n'est plus décrit comme privé.
  - `.gitignore` : documents internes (business plan, audit) exclus du versionnage — décision d'Alexandre du 17/07.
  - **Reste humain** : relecture juridique des deux documents de conformité, passage du dépôt GitHub en public, activation de Dependabot et des Security Advisories, dépôt éventuel de la marque.

## Lancer
`./run.sh` → http://localhost:8000 (bind 127.0.0.1). Données : `~/.local/share/bilan-ortho/` (surchargeable via `BILAN_ORTHO_DATA_DIR`).
