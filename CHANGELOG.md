# Journal des modifications

Toutes les évolutions notables de Bilan Ortho, version par version. Les
numéros suivent la [gestion sémantique de version](https://semver.org/lang/fr/) ;
chaque version correspond à un tag git `v<version>` et, depuis la 1.2.0, à un
installeur Windows publié dans les releases.

## Non publié

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
  des pages déchiffrées effacée, passphrases prévisibles refusées, changement
  de passphrase (re-chiffrement sur place, nouvelle sauvegarde).
- **Parcours d'arrivée** : Ollama absent n'enferme plus dehors un coffre déjà
  installé (bandeau non bloquant et geste qui répare) ; un téléchargement de
  modèle qui échoue n'est plus un cul-de-sac (message en français, autre
  modèle, « passer cette étape »), espace disque vérifié avant, progression en
  mégaoctets ; le domaine du bilan se choisit explicitement ; l'aide s'ouvre à
  la première visite ; le sélecteur de modèle ne ment plus.
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
