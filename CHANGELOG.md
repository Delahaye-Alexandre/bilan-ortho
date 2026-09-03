# Journal des modifications

Toutes les évolutions notables de Bilan Ortho, version par version. Les
numéros suivent la [gestion sémantique de version](https://semver.org/lang/fr/) ;
chaque version correspond à un tag git `v<version>` et, depuis la 1.2.0, à un
installeur Windows publié dans les releases.

## Non publié

Lot B du plan « mise en forme » (`docs/plan-mise-en-forme-2026-09-03.md`) :

- **Mise en page de mes documents** : nouvelle section de ⚙️ Paramètres qui
  règle, pour le Word et le PDF, la police (Calibri, Arial, Verdana, Times
  New Roman, Georgia), la taille du texte, l'interligne, les marges, la
  couleur des titres, la numérotation des rubriques (1. Anamnèse, 2. …) et
  les numéros de page (Page 1 / 3). Tout était jusqu'ici en dur dans
  `app/export.py`, et le praticien finissait dans Word.
- **Logo du cabinet** en tête du document (Word et PDF), déposé en PNG ou
  JPEG depuis l'écran, vérifié et réduit par l'application, rangé dans le
  coffre chiffré (jamais en fichier à part) ; position et hauteur réglables.
- **Aperçu en direct** : un compte-rendu fictif mis en page avec les réglages
  de l'écran, même non enregistrés (`POST /api/config/mise_en_page/apercu`),
  s'affiche sous les réglages et suit chaque changement.
- Le PDF incorpore la police choisie quand son fichier est installé sur la
  machine (Windows en particulier) et prend sinon la police intégrée
  équivalente ; le tableau des résultats suit désormais la largeur utile de
  la page au lieu de déborder quand les marges s'élargissent.
- Section réinitialisable clé par clé (`DELETE /api/config/mise_en_page`,
  le logo a ses routes `PUT`/`DELETE /api/config/logo`). Pillow devient une
  dépendance explicite (elle venait déjà avec reportlab).

- **Date du bilan en heure locale** : un bilan créé entre minuit et 2 h du
  matin (heure d'été) portait la date de la veille, la base datant en temps
  universel. Le test correspondant échouait au même moment.
- **Mise à jour sans passer par GitHub** : quand l'installation intégrée est
  possible (Windows, application installée), le bandeau ne propose plus que
  « Installer maintenant » ; le lien de téléchargement manuel ne réapparaît
  qu'en secours, si cette installation échoue.
- **CI** : le test de mise à niveau ne compare plus les numéros de version
  (entre deux releases, main porte le même numéro que la dernière publiée, ce
  qui refusait tout build après la 1.11.0) : il vérifie que l'application
  relancée est bien celle du build (numéro de `app/__init__.py`, même binaire).

## 1.11.0 — 2026-09-03

Cette version regroupe aussi tout ce qui était prévu pour la 1.10.0, dont le
build n'a jamais abouti (voir la note CI plus bas) : elle n'a pas été publiée.

Plan « Paramètres compréhensibles » (`docs/plan-parametres-2026-09-03.md`) :

- **Des réglages pour orthophonistes, pas pour informaticiens** : l'écran
  ⚙️ Paramètres est réorganisé en six sections dans les mots du cabinet (Mon
  cabinet, Mes comptes-rendus, Ma dictée, Mes tests et seuils, Cotation NGAP,
  Sécurité et sauvegardes), avec un sommaire ; modèles, température, matériel
  de dictée et consigne de structuration sont repliés sous « Réglages
  techniques ».
- **Une bulle d'aide par réglage** : à quoi il sert, quand le changer, et la
  valeur recommandée lue sur le serveur (`GET /api/config/defauts`) ; un
  réglage qui s'en écarte porte la mention « modifié ».
- **Des phrases et des listes à la place des codes** : « Verrouiller l'écran
  après 15 minutes », « jamais », « chaque semaine »… plus de « 0 = jamais » ;
  une valeur inhabituelle déjà enregistrée reste affichée « personnalisée ».
- **L'effet montré en direct** : montant de la cotation (AMO × coefficient),
  quatre scores d'exemple classés selon les seuils (avertissement en clair si
  les seuils sont dans le désordre), aperçu de la signature, état de la
  dictée ; le modèle d'IA se choisit parmi les modèles installés.
- **Revenir aux valeurs recommandées section par section**
  (`DELETE /api/config/{section}`, avec `?cles=`), sans plus effacer identité,
  trame et catalogues ; « Tout rétablir » descend dans le bloc technique.
- **Corrections de dictée littérales** : « ortofonie => orthophonie » remplace
  le mot entier, majuscule ou non ; le préfixe `re:` garde les expressions
  régulières. Le réglage « Vouvoiement » (façon dont l'assistant s'adresse à
  la personne qui dicte) quitte l'écran, sa valeur enregistrée est conservée.

Lot A du plan « mise en forme » (`docs/plan-mise-en-forme-2026-09-03.md`) :

- **Texte riche dans les rubriques** : gras, italique, souligné, listes à puces
  et numérotées, avec une barre de mise en forme par rubrique et les raccourcis
  Ctrl+B / Ctrl+I / Ctrl+U (Entrée = nouveau paragraphe, Maj+Entrée = retour à
  la ligne). Le contenu reste stocké en texte (Markdown restreint,
  `app/texte_riche.py`) : aucune migration, les bilans existants sont inchangés.
- **Exports fidèles** : le Word porte de vrais passages en gras/italique/souligné
  et des listes (chaque liste numérotée repart à 1), le PDF aussi ; Markdown et
  texte brut suivent.
- **Coller depuis Word, LibreOffice ou Google Docs** conserve gras, italique,
  souligné et listes ; tout le reste (polices, couleurs, scripts) est retiré.
  **Copier** place dans le presse-papiers le texte brut et une version HTML,
  pour que la mise en forme survive au collage dans un traitement de texte.
- **La mise en forme du praticien entre dans son style** : l'import Word des
  bilans de référence conserve désormais gras, souligné et listes, et le modèle
  est invité à calquer sa mise en relief sur ces extraits. Réglage
  « L'IA peut mettre en forme » dans ⚙️ Paramètres → Style, actif par défaut ;
  désactivé, les propositions du modèle sont remises en clair avant d'entrer
  dans les rubriques.
- Les vérificateurs de chiffres, de tests cités et d'adossement lisent la
  version en clair : un score en gras reste retrouvé dans la dictée, un numéro
  de liste n'est pas pris pour une valeur clinique.

Mises à jour (`app/maj.py`, plan « mise à jour » validé le 2026-09-03) :

- **Mise à jour en un clic** depuis le bandeau : sauvegarde du coffre,
  téléchargement de l'installeur avec progression, vérification de la
  signature Ed25519 des empreintes publiées (clé publique embarquée) puis de
  l'empreinte du fichier, installation silencieuse, redémarrage sur le même
  port et page qui se reconnecte seule. Un fichier qui échoue à la vérification
  n'est jamais exécuté.
- **Le bandeau dit ce qui change** (nouveautés de la version, date), avec
  « Plus tard » et « Ignorer cette version ».
- **Vérification automatique activée par défaut**, au plus une fois par jour,
  annoncée une fois après le déverrouillage avec le moyen de la désactiver ;
  le bouton « Vérifier maintenant » interroge toujours GitHub.
- **CI** : `SHA256SUMS` et `SHA256SUMS.sig` publiés avec chaque release ;
  test de mise à niveau (version publiée précédente puis celle-ci par-dessus,
  coffre existant rouvert, relance sur le port demandé) ; signature de code
  Windows (Azure Artifact Signing) prête, activée par la seule présence des
  secrets — voir `docs/signature-code.md`. Le test de mise à niveau a bloqué
  les premiers builds : sans Ollama sur le runner, l'installeur silencieux
  téléchargeait Ollama puis attendait sans fin son installeur ; il trouve
  désormais un Ollama factice, l'attente ne couvre plus l'application
  relancée par l'installeur, et l'étape est bornée à vingt minutes.

## 1.9.0 — 2026-09-03

Corrections de la revue complète du 2026-08-11 (v1.8.0 en conditions réelles) :

- **Le compte-rendu ne peut plus partir faux** : export, copie et validation
  proposent d'enregistrer les corrections en cours ; une épreuve mal saisie se
  retire, un bilan se supprime ; plausibilité des étalonnages saisis
  (percentile 0-100, écart-type ±6, notes standard) signalée sans corriger ;
  seuils de drapeaux bornés et ordonnés ; cotation écrite « AMO 24 — 62,40 € » ;
  mention « BROUILLON » sur tout document non validé ; export PDF robuste aux
  interprétations longues.
- **Plus de perte de travail** : confirmation avant de changer de dossier avec
  une dictée ou des rubriques non enregistrées, dictée conservée quand
  l'analyse est à relancer, en-tête et saisie d'épreuve préservés au re-rendu,
  bouton « Annuler l'analyse » effectif jusqu'au serveur, verrouillage qui ne
  laisse plus le dossier à l'écran.
- **Cloisonnement RGPD** : bilans de référence pseudonymisés à l'import et
  rattachables à leur patient (effacés avec lui), purge de conservation qui
  emporte aussi identité et prescription, journal d'audit sans nom de fichier
  ni de destinataire, ce que la suppression emporte et n'emporte pas dit
  clairement.
- **Garde-fous de la chaîne IA** : noms de tests substitués par le modèle
  signalés nommément, rubriques sans ancrage dans la dictée signalées,
  signalements persistés avec le bilan (survivent au rechargement), chiffres
  encore signalés exclus des sources du tour suivant, alerte de dépassement de
  la fenêtre de contexte, aucun texte du modèle perdu en silence, « cent » /
  « mille » / décimales / dates correctement traités.
- **Sécurité du poste** : requêtes modifiantes refusées depuis une page tierce
  (anti-CSRF), modèles Ollama hébergés (« cloud ») refusés partout, bornes sur
  les fichiers envoyés, verrouillage d'inactivité actif même sans requête,
  refus d'écrire des sauvegardes sur un point de montage débranché, mémoire
  des pages déchiffrées effacée (hors Windows), passphrases prévisibles refusées, changement
  de passphrase (re-chiffrement sur place, nouvelle sauvegarde).
- **Parcours d'arrivée** : Ollama absent n'enferme plus dehors un coffre déjà
  installé (bandeau non bloquant et geste qui répare) ; un téléchargement de
  modèle qui échoue n'est plus un cul-de-sac (message en français, autre
  modèle, « passer cette étape »), espace disque vérifié avant, progression en
  mégaoctets ; le modèle de dictée (Whisper) se télécharge depuis l'écran
  d'installation, avant toute dictée ; un enregistrement dont la transcription
  échoue est conservé en mémoire et se réessaie sans redicter ; le domaine du
  bilan se choisit explicitement ; l'aide s'ouvre à la première visite ; le
  sélecteur de modèle ne ment plus.
- **Épreuves** : percentile, note standard et âge de développement saisis à
  part sont enfin pris en compte (drapeau, alerte de plausibilité, export).
- **Coffre** : schéma v2 avec migration transactionnelle et copie de sécurité
  préalable.
- **Docs** : citations du code par symbole, vérifiées par test ; README,
  registre RGPD, notice et versions réalignés sur le code ; ce journal.

## 1.8.0 — 2026-08-11

- Filet de sauvegarde fiabilisé : la restauration ne peut plus détruire le
  coffre qu'elle remplace, ses échecs sont testés.
- Export **PDF** paginé, en plus de Word, Markdown et texte ; en-tête
  professionnel, tableau des résultats d'épreuves, bloc de signature.
- Traçabilité des chiffres : tout nombre proposé par l'IA absent de la dictée
  est signalé rubrique par rubrique.
- Pack de onze bilans **fictifs** d'exemple (un par domaine), chargeable en un
  clic ; import des bilans de référence au format `.odt`.
- README et guide de test : parcours d'arrivée revu pour une première visite.
- Outillage de dépôt public : Dependabot, formulaires de retour, CI au moindre
  privilège, verrou de dépendances surveillé.

## 1.7.0 — 2026-07-22

- Vérification des mises à jour de l'application, opt-in, via l'API GitHub
  Releases (aucune donnée personnelle transmise).

## 1.6.0 — 2026-07-22

Corrections de l'audit du 2026-07-17, lots 9 à 14 :

- Erreurs backend claires et actionnables.
- Saisie protégée et retours immédiats dans l'interface.
- Confidentialité et accès aux données.
- Accessibilité et petits écrans.
- Robustesse persistance et concurrence.
- Restauration guidée des sauvegardes ; éditeurs dédiés pour la trame, les
  catalogues de tests et les prompts.
- Publication open source : licence, charte d'engagements, politique de
  sécurité, documents de conformité.

## 1.5.0 — 2026-07-18

Corrections de l'audit du 2026-07-17, lots 1 à 8 :

- Robustesse frontend : plus aucune perte de saisie ni crash.
- Sécurité réseau et configuration (hôtes contraints à la machine locale).
- Fiabilité backend : le serveur ne gèle plus.
- Intégrité des données : import `.docx` réel et pagination.
- Packaging Windows : mises à jour et téléchargements sûrs.
- CI : lint, matrice multi-versions et multi-OS, lockfile, tests UI.
- Lien de téléchargement en évidence dans le README.

## 1.4.1 — 2026-07-16

- Dictée native réparée : le modèle VAD Silero manquait au build.
- Installeur : arrêt de l'application avant mise à jour ; correctif de
  compilation Inno Setup.
- Vocabulaire neutre dans le guide de test.

## 1.4.0 — 2026-07-16

- Mémoire du dialogue de clarification : les questions répondues ou écartées
  ne sont plus reposées ; panneau des questions enrichi.

## 1.3.1 — 2026-07-11

- Panneau des questions : réponses une à une fiables et envoi groupé.

## 1.3.0 — 2026-07-11

- Modèles à raisonnement (qwen3.5) : `think: false`, réponse en secondes au
  lieu de minutes ; repli automatique pour les anciens Ollama.
- Prompt durci : les extraits de style concernent d'autres patients, toute
  référence à leur contenu est interdite.
- Version unique affichée dans l'interface et renvoyée par `/api/status`.
- Message d'attente honnête pendant la structuration.

## 1.2.1 — 2026-07-05

- Installeur tout-en-un : Ollama téléchargé et installé automatiquement s'il
  est absent ; hors ligne, l'écran guidé de l'app prend le relais.
- Fenêtre d'application dédiée au lieu d'un onglet de navigateur.

## 1.2.0 — 2026-07-05

- Portabilité Windows natif (SQLCipher officiel, données dans
  `%LOCALAPPDATA%`), premier lancement guidé, OCR compatible avec
  l'application compilée.
- Packaging : spec PyInstaller, installeur Inno Setup, build et fumage en CI.
- Guide de test pour les premières personnes utilisatrices.

## 1.1.0 — 2026-07-05

Première version complète : coffre chiffré SQLCipher, dictée vocale locale
(faster-whisper), structuration IA avec questions de clarification (Ollama),
style de l'orthophoniste réinjecté (RAG sqlite-vec), import OCR, patients et
effacement RGPD, sauvegardes chiffrées, cotation NGAP, exports Word et
Markdown, paramètres exhaustifs, lanceur Windows via WSL.
