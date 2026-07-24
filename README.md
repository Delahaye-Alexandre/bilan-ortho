# Bilan Ortho — assistant local de rédaction de bilans orthophoniques

Application **100 % locale** pour orthophonistes : vous **dictez** librement,
l'IA **structure** vos propos dans la trame réglementaire du bilan, **pose des
questions** quand il manque une donnée, s'inspire du **style de vos propres
bilans**, puis vous **relisez, validez, cotez et exportez**.

> ⚠️ **Aide à la rédaction, pas un dispositif de diagnostic.** L'IA *propose* ;
> l'orthophoniste *relit, corrige, valide et signe*. Vous restez seul(e)
> responsable du contenu. Aucune donnée ne quitte votre machine (pas
> d'obligation HDS ; RGPD par conception). Voir `docs/notice-medico-legale.md`
> et `docs/RGPD-registre-traitements.md`.

## ⬇️ Télécharger (Windows)

**[Télécharger Bilan Ortho — installeur Windows](https://github.com/Delahaye-Alexandre/bilan-ortho/releases/latest)**
(Windows 10/11 · installation par utilisateur, sans droits administrateur · le
moteur d'IA local Ollama est installé automatiquement). Guide pas à pas :
[docs/guide-test.md](docs/guide-test.md).

Sous Linux/WSL : voir [Installation & lancement](#installation--lancement)
ci-dessous.

## Fonctionnalités

- **Coffre chiffré** (SQLCipher, AES-256) déverrouillé par passphrase ;
  verrouillage automatique après inactivité ; journal d'audit ;
  **sauvegardes chiffrées** automatiques (au déverrouillage, cadence
  configurable) et manuelles, avec rotation — la copie s'ouvre avec la même
  passphrase.
- **Patients** : fiche minimale (nom, prénom, date de naissance, sexe, notes),
  bilans rattachés, **âge calculé automatiquement** (transmis à l'IA pour les
  étalonnages — jamais l'identité) et porté sur les exports ; suppression d'un
  patient = **effacement RGPD** complet (bilans en cascade).
- **Dictée vocale locale** (faster-whisper, auto-adaptée à votre matériel) :
  l'audio est transcrit en local puis immédiatement supprimé.
- **Structuration IA** (Ollama, local) : la dictée est répartie dans les
  rubriques du tronc commun réglementaire (arrêté du 25/07/2023) et l'assistant
  pose des **questions de clarification** (âge manquant, score sans étalonnage,
  test sans résultat…).
- **Épreuves & scores** : catalogues de tests par domaine (11 domaines),
  interprétation automatique des étalonnages (écart-type, percentile, note
  standard) selon **vos seuils**, phrases-types ajoutées au bilan.
- **Votre style** : importez vos propres bilans (PDF natif, PDF scanné via OCR,
  texte) ; ils sont indexés localement (embeddings + sqlite-vec dans la base
  chiffrée) et réinjectés comme exemples de style à la rédaction. Des amorces
  fictives sont fournies dans `data/reference/`.
- **Cotation NGAP** paramétrable, **cycle de vie** du bilan (brouillon →
  validé → envoyé au prescripteur, tracé) et **export** Word (.docx),
  Markdown, texte.
- **Tout est configurable** depuis l'écran ⚙️ Paramètres : modèles (LLM,
  dictée, embeddings), style (détail, vouvoiement, nb d'exemples), seuils,
  cotation, RGPD (verrouillage, durée de conservation — l'audio de dictée est,
  lui, toujours supprimé), et même la **trame des bilans**, les **catalogues de
  tests** et la **consigne de structuration**, chacun avec son éditeur dédié —
  sans toucher au code.

## Prérequis

- Python 3.12+, [Ollama](https://ollama.com) lancé (`ollama serve`)
- Modèles Ollama :
  ```bash
  ollama pull qwen2.5:7b-instruct-q4_K_M   # LLM (défaut de la config, ~4 Go)
  ollama pull nomic-embed-text             # embeddings (défaut, léger)
  # option qualité FR : ollama pull bge-m3  (embeddings, ~1,2 Go)
  ```
  > Pourquoi deux familles de LLM ? `qwen2.5:7b` reste le **défaut de la
  > config** ; l'écran « 🚀 Première installation » propose, lui, `qwen3.5:9b`
  > (machines ≥ 16 Go de RAM) ou `qwen3.5:4b` (8 Go), de meilleure qualité en
  > français. Le modèle se change à tout moment dans ⚙️ Paramètres.
- **Optionnel — OCR des PDF scannés** :
  ```bash
  sudo apt install tesseract-ocr tesseract-ocr-fra
  pip install ocrmypdf
  ```

> N'utilisez **jamais** de modèle `:cloud` sur des données patient : tout doit
> rester local.

## Installation & lancement

```bash
cd ~/projects/bilan-ortho
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh            # → http://localhost:8000 (bind 127.0.0.1 uniquement)
```

### Lancement en un clic (Windows/WSL)

`BilanOrtho.exe` (sur le Bureau, source dans `packaging/windows/`) : double-clic
→ démarre le serveur dans WSL s'il ne tourne pas déjà (via
`scripts/start-serveur.sh`, silencieux et idempotent — jamais de doublon), puis
ouvre l'app dans une **fenêtre dédiée** (mode application d'Edge/Chrome, sans
onglets ni barre d'adresse ; repli navigateur classique si absent). Recompiler après modification :
`packaging/windows/build.sh bureau` (utilise le compilateur C# intégré à
Windows, rien à installer). Journaux :
`~/.local/share/bilan-ortho/serveur.log` (et `ollama.log`).

Au premier lancement, créez la **passphrase** de votre coffre : elle chiffre
toutes les données et est **irrécupérable** en cas d'oubli.

Les données vivent dans `~/.local/share/bilan-ortho/` (surchargeable via
`BILAN_ORTHO_DATA_DIR`). Hôte/port : `BILAN_ORTHO_HOST` / `BILAN_ORTHO_PORT` ;
Ollama : `OLLAMA_HOST`.

## Parcours type

1. **Patient** (bouton 👤) puis **nouveau bilan** : domaine + type
   (simple / complexe / renouvellement) — la date de naissance permet à
   l'assistant de connaître l'âge sans le redemander.
2. **Dictée** : parlez librement (ou tapez) ; transcription 100 % locale.
3. **Structurer** : l'IA remplit les rubriques et pose ses questions ;
   répondez-y (voix ou clavier), le bilan se complète.
4. **Épreuves & scores** : saisissez chaque test ; le drapeau
   norme / fragilité / pathologique / sévère est déduit de vos seuils.
5. **Relire & valider** chaque rubrique (badge « à valider » → « validé »).
6. **Coter** (NGAP), **exporter** (Word / Markdown / copie), puis marquer le
   bilan **validé** et **envoyé** (destinataire tracé).

Pour le style : importez 2-3 de vos bilans dans « Mes bilans de référence »
(commencez avec `data/reference/` si vous n'en avez pas sous la main).

## Sauvegarde & restauration

Une sauvegarde chiffrée du coffre est créée automatiquement au déverrouillage
si la dernière date de plus de N jours (défaut 7), et à la demande depuis
⚙️ Paramètres. Dossier par défaut : `<données>/sauvegardes` — configurez
plutôt un support externe (clé USB, disque). La copie reste chiffrée : **elle
ne s'ouvre qu'avec votre passphrase**.

**Restaurer** : depuis ⚙️ Paramètres → « Sauvegarde du coffre », bouton
« Restaurer… » en face de la copie voulue. L'application vérifie que la copie
s'ouvre avec votre passphrase, crée d'abord une sauvegarde de vos données
actuelles, puis échange les fichiers et se reconnecte. En dernier recours, la
procédure manuelle reste possible : application arrêtée, remplacez
`~/.local/share/bilan-ortho/bilan.db` par la copie (renommée `bilan.db`), puis
relancez et déverrouillez avec la même passphrase.

## Dictée : choix du modèle

Par défaut (`auto`), l'app choisit selon votre matériel : GPU ≥ 6 Go VRAM →
`large-v3`, sinon CPU + `medium` (int8). Le modèle se télécharge au premier
usage (~1,5 Go pour `medium`). Pour la meilleure qualité FR, pointez
`Paramètres → Dictée → Modèle` vers un modèle CTranslate2 fine-tuné français
(ex. conversion de `bofenghuang/whisper-large-v3-french`).

## Tests

```bash
pip install pytest
pytest tests/        # 100 % hors ligne (LLM/embeddings mockés ;
                     # le test OCR est sauté si Tesseract n'est pas installé)
bun tests/ui/test_questions_ui.mjs    # tests UI (happy-dom) : panneau questions
bun tests/ui/test_robustesse_ui.mjs   # tests UI : brouillons, 423, anti double-clic
pip install ruff && ruff check .      # lint (config dans pyproject.toml)
```

## Structure

```
bilan-ortho/
├── app/
│   ├── main.py         # API FastAPI (bind localhost, TrustedHost)
│   ├── security.py     # coffre, verrouillage, audit, purge RGPD
│   ├── db.py           # schéma SQLCipher + sqlite-vec + migrations
│   ├── config.py       # défauts + surcharges praticien (en base)
│   ├── models.py       # modèles Pydantic (validation des échanges)
│   ├── systeme.py      # état machine (RAM, Ollama, modèles) — 1er lancement guidé
│   ├── stt.py          # dictée locale (faster-whisper, auto-adaptative)
│   ├── llm.py          # client Ollama (structuration JSON, timeout borné)
│   ├── prompts.py      # prompts (structuration, clarification, style)
│   ├── bilan.py        # CRUD bilan, épreuves, interprétation étalonnages
│   ├── patient.py      # patients, âge, effacement RGPD
│   ├── sauvegarde.py   # copies chiffrées du coffre (VACUUM INTO, rotation)
│   ├── catalogues.py   # tests étalonnés par domaine
│   ├── cotation.py     # NGAP paramétrable
│   ├── rag.py          # embeddings + recherche « style du praticien »
│   ├── importer.py     # import PDF/OCR/.docx/texte → découpage → indexation
│   ├── export.py       # Word / Markdown / texte
│   └── static/         # interface web (vanilla, servie par FastAPI)
├── data/reference/     # bilans fictifs d'amorce (style)
├── docs/               # recherche, notice médico-légale, registre RGPD, avancement
├── packaging/          # spec PyInstaller + installeur Inno Setup (Windows)
├── tests/              # pytest (hors ligne) + tests UI happy-dom (bun) dans ui/
├── lanceur.py          # point d'entrée natif (PyInstaller) : port, fenêtre, journal
├── requirements.txt    # dépendances (souples) — versions figées : requirements.lock
└── run.sh
```

## Distribution (Windows natif)

Le dépôt GitHub (`Delahaye-Alexandre/bilan-ortho`) construit tout via
Actions : tests sur Windows + Linux, binaire PyInstaller (`lanceur.py` →
`dist/BilanOrtho/`), fumage du binaire, installeur Inno Setup
(`packaging/windows/installeur.iss`, installation par utilisateur sans
droits admin). Un tag `v*` **publie** la Release avec son installeur sur la
[page des versions](https://github.com/Delahaye-Alexandre/bilan-ortho/releases),
accompagnée de `docs/guide-test.md` (SmartScreen, premier lancement guidé,
parcours d'essai). Les données vivent dans `%LOCALAPPDATA%\bilan-ortho` (préservées à
la désinstallation).

> **Publier la release, ne pas la laisser en brouillon.** L'API
> `releases/latest` ignore les brouillons : la vérification de mise à jour
> intégrée à l'application (`app/maj.py`) ne verrait pas la nouvelle version,
> et les personnes déjà équipées ne sauraient pas qu'elle existe.

## Licence & engagements

Bilan Ortho est un logiciel libre publié sous licence **AGPL v3** (fichier
[LICENSE](LICENSE)). Les engagements publics du projet — données locales, IA
jamais entraînée sur vos données, validation humaine systématique, gratuité
pérenne — sont détaillés dans la
[charte d'engagements](docs/charte-engagements.md). Voir aussi la
[politique de sécurité](SECURITY.md) et les documents de conformité dans
[docs/conformite/](docs/conformite/) (auto-évaluation AI Act et déclaration de
finalité MDR).

## Avertissement médico-légal

Ce logiciel ne pose aucun diagnostic et ne remplace pas le jugement clinique.
Les valeurs NGAP évoluent par avenants : vérifiez-les sur ameli.fr (elles sont
modifiables dans les paramètres). Avant tout usage sur données réelles de
patients, faites valider votre organisation par un DPO / juriste santé
(consentement à l'enregistrement vocal notamment). Détails :
`docs/notice-medico-legale.md`.
