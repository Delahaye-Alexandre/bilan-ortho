# Recherche consolidée — bilan-ortho (juillet 2026)

Trois volets de recherche pour concevoir l'app pro d'aide à la rédaction de bilans orthophoniques.

---

## VOLET 1 — Sources de bilans "libres de droits" et statut juridique

**Point juridique clé (exploitable) :** la *structure* du compte-rendu de bilan orthophonique (CRBO) est **imposée par un texte réglementaire** (arrêté 25/07/2023, convention/NGAP). Une structure imposée par la loi + de simples intitulés de rubriques ne sont **pas protégeables** → reproductibles librement. En revanche les **formulations rédigées** d'un auteur restent protégées par droit d'auteur.

**Conséquence design "base de bilans de référence" :**
- Socle sûr = **structure réglementaire officielle** (Légifrance, FNO, Collège Français d'Orthophonie, HAS) — réutilisable.
- **+ Exemples rédigés que l'on écrit soi-même** (données fictives).
- **+ Les propres bilans de l'orthophoniste** (ses données, importés localement) → c'est là qu'est la vraie valeur du style.
- **À NE PAS redistribuer :** trames d'auteurs (Orthonie, myCR, Scribd, myodefi, HappyNeuron…) — téléchargeables ≠ libres de droits.

**Sources structure/cadre (réutilisables comme référence) :**
- Arrêté 25/07/2023 + avenants — Légifrance (licence ouverte, le plus sûr)
- FNO — note CRBO : https://fno.fr/wp-content/uploads/2024/11/NS2016_2017-note-aux-orthos-CRBO-1.pdf
- Collège Français d'Orthophonie — RECOS langage écrit : https://www.college-francais-orthophonie.fr/wp-content/uploads/2022/03/RECOS_LE.pdf
- HAS/ANAES — troubles langage écrit : https://sante.gouv.fr/IMG/pdf/04.ortho_anaes.pdf
- Mémoires universitaires (PEPITE Lille, Bibnum Lyon) — grilles en annexes (usage pédagogique, citer l'auteur)

**Specimens rédigés librement consultables (INSPIRATION seulement) :**
- Orthonie — 8 modèles Word CRBO (langage oral/écrit, logico-math, voix, déglutition, OMF, bégaiement, cognition/aphasie) : https://orthonie.fr/modeles-crbo-gratuits
- myCR — exemple PDF complet : https://mycr.fr/blog/exemple-compte-rendu-bilan-orthophonique
- Scielle — structure + tableaux de scores : https://scielle.com/blog/modele-compte-rendu-bilan-orthophonique
- Seule licence CC trouvée : orthophonielibre.wordpress.com — mais ce sont des outils de rééducation, PAS des trames de bilan.

**Tronc commun de sections (tout bilan) :**
1. Données administratives / objet (identité, prescripteur, date, type de bilan)
2. Anamnèse (médicale, développementale, familiale, scolaire ; motif/plaintes)
3. Observations cliniques qualitatives (comportement, attention, coopération)
4. Épreuves/tests + résultats chiffrés (brut + étalonnage) + interprétation
5. Analyse / synthèse clinique
6. Diagnostic orthophonique (+ cotation NGAP)
7. Projet thérapeutique / préconisations
8. Mentions obligatoires (signature, envoi médecin, DMP)

---

## VOLET 2 — Structure clinique réglementaire + tests

**Cadre (juillet 2026, post-avenant 21 en vigueur depuis 23/02/2026) :** bilan = acte réservé sur prescription médicale → CRBO obligatoire → diagnostic orthophonique posé **en autonomie par l'orthophoniste** → CR adressé au médecin prescripteur (quelles que soient les conclusions) + DMP.

**11 domaines (entité pivot du schéma) :** langage oral · langage écrit · parole/articulation/phonologie · cognition mathématique · communication & handicap/TSA · voix · déglutition/OMF · neuro acquise (aphasie/dysarthrie/neurodégénératif) · surdité · bégaiement/fluence · oralité alimentaire nourrisson. Le domaine conditionne tests, cotation, vocabulaire diagnostique, rubriques.

**Cotation NGAP (post-avenant 21, valeur AMO 2,60 € métropole — À PARAMÉTRER, pas coder en dur) :**
- Bilan simple (initial) : AMO 24 · Bilan complexe (initial) : AMO 34 · Renouvellement : AMO 30
- Suppression de la DAP → contrôle en aval → CR structuré/justifié encore plus important.

**Tests standardisés par domaine (extrait) :**
- Langage oral : EVALO 2-6, N-EEL, ELO, BILO, EXALANG 3-6, EVIP/TVAP, ECOSSE, TCG-R, IFDC
- Langage écrit : Alouette-R (âge de lecture), EVALEO 6-15, EXALANG 5-8/8-11/11-15, ODEDYS-2, BALE, EVALEC, ELFE (fluence), Chronodictées, L2MA-2
- Cognition math : TEDI-MATH (+GRANDS), ZAREKI-R, EXAMATH, UDN-II
- Neuro adulte : MT-86, BDAE, BIA, GRÉMOTS, Token Test, DO 80, fluences verbales
- Voix : GRBAS/GIRBAS, VHI, CAPE-V, analyse acoustique (F0, jitter, shimmer, TMP)
- Déglutition : EAT-10, DHI, essais texturés ; Bégaiement : %SS, SSI-4/Riley, OASES
- OMF/praxies : MBLF ; Oralité nourrisson & TSA : surtout grilles/questionnaires qualitatifs

**Restitution des résultats (règle d'or : jamais un score brut seul) :**
- Métriques : écart-type (ET/z), percentile, note standard (moy 10, ET 3), âge de développement/lecture, note étalonnée
- Seuils : -1,5 ET (≈7e pct) = zone patho standard ; -1 à -1,5 ET = fragilité ; -1,65 ET (≈5e pct, EXALANG 8-11/11-15) ; -2 ET (≈2e pct) = sévère
- Nuance psychométrique à afficher : plusieurs batteries (ELO, N-EEL, EXALANG, L2MA-2) ne remplissent pas tous les critères psychométriques → contextualiser (date d'étalonnage, marge d'erreur).

**Contraintes produit critiques (déontologie) :**
- L'outil ne pose **JAMAIS** un diagnostic seul ni comme définitif → l'IA **propose**, l'orthophoniste **valide et signe**. Garde-fou UX explicite.
- Exiger/enregistrer prescription (prescripteur + date + libellé). Cas dérogatoire : intervention sans prescription (établissements santé mentale, médico-social).
- Secret professionnel (L4344-2 CSP) ; responsabilité pleine de l'orthophoniste (L4341-9).

---

## VOLET 3 — Stack technique locale (STT FR, RGPD, RAG)

**STT français local (dictée) :**
- **Choix principal : faster-whisper (CTranslate2)** + modèle FR fine-tuné **`bofenghuang/whisper-large-v3-french`** (MIT, format CT2). WER ~4,8-7,3 %.
  - GPU ≥6 Go : large-v3-french en float16/int8_float16 → qualité max quasi temps réel.
  - CPU : `whisper-large-v3-french-distil-dec8` en int8 → dictée par segments.
  - Toujours `vad_filter=True` (VAD Silero intégré).
- **Vocabulaire métier :** `hotwords` (glossaire ortho : praxies, phonologie, noms de tests…) + `initial_prompt` (≤224 tokens, style seulement) + **post-correction déterministe** (dico regex/fuzzy).
- **Streaming temps réel (option) :** WhisperLiveKit (serveur FastAPI/WebSocket, faster-whisper) ou Kyutai `stt-1b-en_fr` (latence ~0,5 s, FR natif).
- **⚠️ Web Speech API navigateur = PAS local** (envoi Google) → proscrit pour du médical. STT côté backend local, le navigateur n'envoie l'audio qu'au localhost.

**RGPD / données de santé (app 100 % locale) :**
- App strictement locale = **PAS d'obligation HDS** (HDS ne vise que l'hébergement par un tiers). Dès qu'un tiers/cloud touche les données → HDS obligatoire. → tout garder local (Ollama + Whisper locaux).
- RGPD s'applique quand même : registre des traitements (art. 30), base légale + info/consentement à l'enregistrement vocal, minimisation (supprimer l'audio après validation du texte), pseudonymisation, durée de conservation, droits d'accès/effacement.
- Sécurité CNIL : chiffrement disque + sauvegardes, contrôle d'accès (mdp, verrouillage inactivité), journalisation, sauvegardes hors site.
- Chiffrement base : **SQLCipher via `sqlcipher3-binary`** (PAS `pysqlcipher3` non maintenu) + LUKS/BitLocker disque.

**RAG "apprendre du style de l'orthophoniste" :**
- Embeddings : **`bge-m3` via Ollama** (`ollama pull bge-m3`, meilleure qualité FR + 1 seul runtime) ; alt : multilingual-e5-large.
- Base vectorielle : **`sqlite-vec`** (mono-fichier, dans la même base SQLite chiffrée, + FTS5 pour hybride, mode WAL). Alt : LanceDB si gros volume.
- OCR bilans scannés FR : **OCRmyPDF + Tesseract `fra`** par défaut → PaddleOCR pour scans dégradés.
- Few-shot style transfer : découper les bilans par section + métadonnées (section, domaine) → au moment de rédiger, récupérer top-k (3-5) extraits de la **même personne**, même section, domaine proche, longueur comparable → injecter comme exemples dans le prompt Ollama. Pas de fine-tuning.

**Stack finale :** FastAPI (existant) + Ollama (LLM, déjà là) + faster-whisper (STT) + bge-m3 (embeddings) + sqlite-vec (dans base SQLCipher) + OCRmyPDF/Tesseract (OCR).
