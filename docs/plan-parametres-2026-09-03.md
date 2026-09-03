# Plan « Paramètres compréhensibles » — validé le 2026-09-03

## Constat de départ

L'écran ⚙️ Paramètres est une seule modale de douze cadres, dans l'ordre où
les réglages sont arrivés dans le code, avec le vocabulaire du code :
« Modèle LLM », « Température », « Faisceau (beam) », « VAD », « Modèle
d'embeddings », « regex », « cuda ». Les personnes qui utilisent Bilan Ortho
sont orthophonistes, pas informaticiennes : elles ne savent ni ce que ces
mots désignent, ni si elles doivent y toucher, ni ce qui se passe si elles
le font.

Ce qui manque, concrètement :

- **Aucune hiérarchie** : la valeur de la lettre-clé AMO (qui change à chaque
  avenant) et la taille de faisceau de Whisper (qui ne change jamais) ont le
  même poids visuel. Le premier réglage affiché, avec le focus, est « Modèle
  LLM » en texte libre.
- **Presque aucune aide** : quelques lignes grises, aucune bulle. Un réglage
  ne dit ni à quoi il sert, ni sa valeur recommandée, ni quand le changer.
- **Des conventions de développeur** : « 0 = jamais », « 0 = sans limite »,
  « vide = la ville », « motif => remplacement, regex », valeurs négatives
  pour les seuils (un avertissement de trois lignes compense un libellé
  ambigu).
- **Du texte libre là où l'application connaît les bonnes valeurs** : le
  modèle d'IA se tape à la main alors que la barre principale offre déjà la
  liste des modèles installés (`GET /api/models`).
- **Un seul « Rétablir les défauts »**, qui efface tout — vocabulaire, seuils,
  cotation, trame, catalogues, consigne — quand on voulait seulement annuler
  un essai sur un réglage.
- **Un libellé faux** : « Vouvoiement » laisse croire qu'il s'agit du
  compte-rendu, alors qu'il règle la façon dont l'assistant s'adresse à la
  personne qui dicte (`prompts.py`).

## Principes

1. **Deux niveaux.** « Mes réglages » (ce qui a un effet sur le cabinet, le
   document, la dictée, la sécurité) visibles d'emblée ; « Réglages
   techniques » repliés, avec un avertissement et le rappel que les valeurs
   proposées conviennent.
2. **Une bulle ⓘ par réglage** : à quoi ça sert, valeur recommandée, quand la
   changer, ce qui se passe. Trois phrases au plus, sans mot de code.
3. **Le vocabulaire du cabinet.** Des phrases complètes plutôt que des
   étiquettes : « Verrouiller l'écran après 15 minutes sans activité ».
4. **Montrer l'effet.** La cotation affiche le montant calculé, les seuils
   affichent un exemple de score classé, l'identité affiche la signature telle
   qu'elle sortira.
5. **Réversible sans peur.** Un réglage modifié est marqué, chaque section a
   son « Revenir aux valeurs recommandées », le « tout rétablir » global
   descend dans le bloc technique.
6. **Rien de nouveau côté données.** Mêmes clés de configuration, mêmes routes
   d'enregistrement ; s'ajoutent seulement une lecture des défauts et un
   retour aux défauts par section.

## Nouvelle organisation

Un sommaire en tête de modale (liens qui font défiler jusqu'à la section).
Le focus à l'ouverture se pose sur le premier champ de « Mon cabinet ».

| Section | Réglages | Clés de config |
|---|---|---|
| 🪪 **Mon cabinet** | identité professionnelle + **aperçu de la signature** | `praticien.*` |
| 📝 **Mes comptes-rendus** | niveau de détail ; « L'assistant peut mettre en forme » (lot A) ; « S'inspirer de mes bilans de référence » ; **trame des bilans** (éditeur existant, déplacé ici) | `style.niveau_detail`, `style.mise_en_forme_ia`, `style.few_shot_k`, `trame` |
| 🎤 **Ma dictée** | vocabulaire à reconnaître ; mots à corriger ; état de la dictée (modèle et matériel en cours, lecture seule) | `stt.hotwords`, `stt.corrections` |
| 📊 **Mes tests et seuils** | seuils en écarts-types et en percentiles + **exemple vivant** ; catalogues de tests (éditeur existant, déplacé ici) | `seuils.*`, `catalogues` |
| 💶 **Cotation NGAP** | valeur AMO, trois coefficients + **montants calculés** | `cotation.*` |
| 🔒 **Sécurité et sauvegardes** | verrouillage après inactivité ; durée maximale d'une dictée ; conservation des bilans ; changement de passphrase ; sauvegarde (dossier, copies, automatique, sauvegarder maintenant, restaurer) ; mises à jour | `rgpd.*`, `sauvegarde.*`, `maj.*` |
| 🔧 **Réglages techniques** (replié) | modèle d'IA (**liste des modèles installés**), température, modèle de lecture des bilans de référence ; matériel, modèle de reconnaissance vocale, faisceau, langue, filtrage des silences ; consigne de structuration (éditeur existant) ; « Tout rétablir » | `llm.model`, `llm.temperature`, `embeddings.model`, `stt.device`, `stt.model`, `stt.beam_size`, `stt.language`, `stt.vad`, `prompts.structure_system` |

Non exposés, comme aujourd'hui : `llm.host`, `llm.num_ctx`, `llm.timeout_s`,
`llm.max_car_section`, `stt.compute_type`, `embeddings.host`, et désormais
`style.vouvoiement` (décision 6).

## Libellés : avant → après

| Avant | Après |
|---|---|
| Modèle LLM (texte libre) | Modèle d'intelligence artificielle (liste des modèles installés, « non installé » signalé comme dans la barre principale) |
| Température (0 = factuel) | Liberté de formulation de l'assistant (0 à 1) |
| Modèle d'embeddings (indexation de mes bilans) | Modèle de lecture de mes bilans de référence |
| Matériel : auto / cpu / cuda (GPU) | Composant utilisé pour la dictée : Automatique / Processeur / Carte graphique |
| Modèle Whisper | Précision de la reconnaissance vocale : Automatique / tiny … large-v3 (le chemin libre reste possible) |
| Faisceau (beam) | Hypothèses examinées par la reconnaissance vocale |
| Langue | Langue des dictées |
| Filtrer les silences (VAD) | Ignorer les silences et bruits de fond |
| Vocabulaire métier (un terme par ligne — aide la reconnaissance) | Mots que la dictée doit connaître (un par ligne) |
| Corrections automatiques (motif => remplacement, regex) | Mots à corriger après la dictée (une ligne par correction : `entendu => voulu`) |
| Extraits de mes bilans injectés | S'inspirer de mes bilans de référence : Non / Un peu / Normalement / Beaucoup |
| Niveau de détail | Longueur des rubriques rédigées : Concis / Standard / Détaillé |
| Vouvoiement | retiré de l'écran (décision 6) |
| Seuils d'interprétation — Fragilité ≤ | Signaler « fragilité » à partir de … écart-type (et de suite) |
| Valeur AMO (€) / Coeff. bilan simple… | Valeur de la lettre-clé AMO / Coefficient du bilan simple… + ligne « Bilan simple : 24 × 2,60 € = 62,40 € » |
| Verrouillage après inactivité (min, 0 = jamais) | Verrouiller l'écran après … minutes sans activité (choix : 5, 15, 30, 60, jamais) |
| Durée max d'une dictée (min, 0 = sans limite) | Arrêter d'elle-même une dictée après … minutes (choix : 10, 30, 60, jamais) |
| Conservation des bilans (jours, 0 = illimitée) | Supprimer automatiquement les bilans non modifiés depuis … (choix : jamais, 1 an, 2 ans, 5 ans, autre) |
| Dossier (vide = données/sauvegardes) | Dossier des sauvegardes (vide : dossier de l'application) |
| Copies conservées | Nombre de sauvegardes gardées |
| Auto au déverrouillage (jours, 0 = off) | Sauvegarder automatiquement à l'ouverture si la dernière date de plus de … (chaque jour / chaque semaine / chaque mois / jamais) |
| Rétablir les défauts | Tout rétablir (bloc technique) + « Revenir aux valeurs recommandées » par section |

Les listes à choix conservent une valeur inhabituelle déjà enregistrée
(p. ex. 3 jours) sous une entrée « 3 jours (personnalisé) » : on ne change
jamais un réglage à l'insu de la personne en ouvrant l'écran.

## Bulles d'info

### Mécanique

- Un bouton `ⓘ` après chaque libellé (hors du `<label>`, pour ne pas
  capturer le clic du libellé), `aria-label="Aide sur ce réglage"`.
- Les textes vivent dans un seul objet `AIDES` (identifiant du champ → texte)
  dans `index.html` ; au chargement, chaque bouton reçoit sa bulle
  (`role="tooltip"`) et le champ son `aria-describedby`.
- Affichée au survol et au focus clavier (CSS), **épinglée au clic** (tactile,
  et pour la lire tranquillement) ; une seule bulle épinglée à la fois ;
  Échap ferme d'abord la bulle, puis, au second appui, la modale.
- La bulle affiche la **valeur recommandée** lue depuis les défauts du serveur
  (nouvelle route `GET /api/config/defauts`), jamais recopiée à la main : elle
  ne peut pas se périmer.
- Un champ dont la valeur diffère du défaut porte une pastille « modifié »
  (surcharges lues via `GET /api/config/overrides`, déjà utilisé par les
  éditeurs).

### Textes proposés

Ils sont la matière à valider : c'est ce que liront les orthophonistes.
Vocabulaire neutre, aucune formulation qui laisse entendre que l'assistant
diagnostique ou décide.

**Mon cabinet**

- *Section* — Ces informations apparaissent en en-tête et en signature de vos
  comptes-rendus exportés. Non renseignées, le document sort sans en-tête :
  rien n'est inventé à votre place.
- *Titre* — Tel qu'il figurera sous votre signature (« Orthophoniste »,
  « Orthophoniste D.E. »…).
- *ADELI, RPPS* — Reportés dans l'en-tête, comme sur vos ordonnances.
  Facultatifs.
- *SIRET* — Facultatif ; utile si vos comptes-rendus tiennent lieu de
  document administratif.
- *Lieu de signature* — Complète la formule « Fait à …, le … » en fin de
  document. Vide : la ville de votre adresse.

**Mes comptes-rendus**

- *Longueur des rubriques* — Degré de développement des rubriques que
  l'assistant rédige à partir de votre dictée. « Concis » va à l'essentiel,
  « Détaillé » développe davantage. Rien n'est ajouté qui ne vienne de votre
  dictée : seule la longueur change.
- *L'assistant peut mettre en forme* (lot A) — Autorise gras, italique,
  souligné et listes, sobrement et à l'image de vos bilans de référence.
  Décoché : texte simple, vous mettez en forme vous-même.
- *S'inspirer de mes bilans de référence* — Nombre de passages de vos bilans
  importés montrés à l'assistant pour qu'il adopte votre façon d'écrire.
  « Non » : il n'en tient pas compte. Sans bilans importés, ce réglage est
  sans effet.
- *Trame des bilans* — Rubriques créées pour chaque nouveau bilan, dans cet
  ordre. La trame intégrée suit l'arrêté du 25 juillet 2023 et les mises à
  jour de l'application ; une trame personnalisée ne bouge plus tant que vous
  n'y revenez pas. Les bilans existants ne changent pas.

**Ma dictée**

- *Mots que la dictée doit connaître* — Termes que la reconnaissance écorche :
  noms de tests, termes techniques, prénoms fréquents. Un par ligne. Elle les
  privilégie quand elle hésite. Quelques dizaines suffisent.
- *Mots à corriger* — Remplacements appliqués au texte dicté, une ligne par
  correction : ce que la dictée écrit, la flèche `=>`, ce que vous voulez.
  Exemple : `ortofonie => orthophonie`. Le mot entier est remplacé, avec ou
  sans majuscule.
- *État de la dictée* (lecture seule) — Modèle et composant en cours, choisis
  automatiquement selon votre machine. Pour changer précision ou vitesse :
  réglages techniques.

**Mes tests et seuils**

- *Section* — Quand vous saisissez un score, l'application le compare à ces
  seuils pour proposer un repère : fragilité, pathologique, sévère. C'est une
  aide à la lecture des étalonnages ; l'interprétation vous appartient.
- *En écarts-types* — Un score inférieur ou égal au seuil reçoit le repère.
  Les seuils s'écrivent en négatif et se suivent du moins sévère au plus
  sévère ; l'exemple ci-dessous montre ce que donnent vos valeurs.
- *En percentiles* — Mêmes repères pour les tests étalonnés en rang sur 100.
  Les valeurs usuelles 16, 7 et 2 correspondent à −1, −1,5 et −2
  écarts-types.
- *Catalogues de tests* — Tests proposés à la saisie d'une épreuve, domaine
  par domaine, avec des orientations de rédaction rappelées à l'assistant.
  Ajoutez les vôtres ; le catalogue intégré suit les mises à jour tant que
  vous ne le personnalisez pas.

**Cotation NGAP**

- *Valeur de la lettre-clé AMO* — En euros, fixée par la convention (source :
  ameli.fr). Elle change par avenant : mettez-la à jour à chaque publication.
- *Coefficients* — Coefficients de la nomenclature pour chaque type de bilan.
  Montant = AMO × coefficient ; le calcul s'affiche en dessous.

**Sécurité et sauvegardes**

- *Verrouiller l'écran* — Passé ce délai sans activité, la passphrase est
  redemandée, comme une session Windows. Protège un poste laissé ouvert au
  cabinet. « Jamais » est déconseillé sur un poste partagé.
- *Arrêter une dictée* — Une dictée en cours maintient l'application
  déverrouillée ; cette limite évite qu'un micro oublié ne la laisse ouverte.
- *Supprimer automatiquement* — Un bilan non modifié depuis ce délai est
  supprimé à l'ouverture de l'application, avec ses données. « Jamais » :
  vous gérez la conservation vous-même, dans le respect des durées légales.
- *Passphrase* — Une phrase entière, plus facile à retenir et plus solide
  qu'un mot de passe. Irrécupérable : personne ne peut la retrouver, pas même
  l'auteur de l'application.
- *Dossier des sauvegardes* — Où déposer les copies chiffrées. Idéalement un
  autre support que le disque de l'ordinateur (clé USB, disque externe) :
  une panne emporterait sinon données et sauvegardes.
- *Nombre de sauvegardes gardées* — Au-delà, la plus ancienne est effacée.
- *Sauvegarder automatiquement* — À l'ouverture, une copie est faite si la
  dernière est plus ancienne que ce délai.
- *Mises à jour* — texte existant conservé.

**Réglages techniques**

- *Avertissement de bloc* — Ces réglages touchent au fonctionnement interne.
  Les valeurs proposées conviennent à la grande majorité des installations ;
  ne les changez que sur conseil ou en connaissance de cause. « Revenir aux
  valeurs recommandées » annule vos modifications de ce bloc.
- *Modèle d'intelligence artificielle* — Programme installé sur votre
  machine (par Ollama) qui range votre dictée dans les rubriques. Seuls les
  modèles installés sont proposés. Plus gros : généralement plus juste, plus
  lent. Aucun modèle « en ligne » n'est accepté : vos données restent ici.
- *Liberté de formulation* — 0 : la plus fidèle et la plus prévisible.
  Au-delà de 0,5, l'assistant reformule davantage, au risque de s'éloigner
  de votre dictée.
- *Modèle de lecture des bilans de référence* — Retrouve, dans vos bilans
  importés, les passages proches de votre dictée. En changer oblige à
  réimporter vos bilans de référence.
- *Composant pour la dictée* — « Automatique » prend la carte graphique si
  elle est assez puissante, sinon le processeur.
- *Précision de la reconnaissance vocale* — Plus grand : plus précis, mais
  plus lent et plus gourmand. « Automatique » choisit selon votre machine.
- *Hypothèses examinées* — Nombre de transcriptions comparées avant de
  retenir la meilleure. Plus élevé : un peu plus précis, un peu plus lent.
- *Langue des dictées* — Code à deux lettres ; `fr` pour le français.
- *Ignorer les silences* — À décocher seulement si des débuts de phrases
  sont coupés.
- *Consigne de structuration* — Modifier ce texte change la façon dont
  l'assistant range votre dictée dans les rubriques. La consigne intégrée
  suit les mises à jour ; une consigne personnalisée ne bouge plus. À
  réserver aux personnes à l'aise avec ce genre d'outil.

## Réglages qui parlent

- **Cotation** : sous les quatre champs, une ligne recalculée à la frappe :
  « Bilan simple : 24 × 2,60 € = 62,40 € · complexe : 88,40 € ·
  renouvellement : 78,00 € ». Même règle de calcul et même format que
  `cotation.py` (deux décimales, virgule).
- **Seuils** : « Avec ces valeurs : −0,8 ET → norme · −1,3 → fragilité ·
  −1,7 → pathologique · −2,4 → sévère », recalculée à la frappe avec la
  règle de `bilan.py` (comparaison ≤). Les incohérences (seuils dans le
  désordre, valeur positive) sont dites en clair au lieu du 422 du serveur.
- **Identité** : « Signé : Prénom Nom, Orthophoniste — N° ADELI … — Fait à
  Ville », mis à jour à la frappe, pour vérifier sans exporter.
- **Dictée** : « En cours : modèle small, sur processeur (choix automatique) »
  depuis `GET /api/stt/info`, déjà appelé pour la barre principale.
- **Modèle d'IA** : liste `GET /api/models`, entrée « (non installé) » en
  tête si le modèle configuré manque, comme dans `loadLLM` (fonction
  généralisée pour remplir les deux listes).

## Décisions validées le 2026-09-03

1. Sommaire et défilement. 2. Corrections littérales, préfixe `re:`. 3. Listes à
choix. 4. Retour par section. 5. Trame et catalogues déplacés. 6. « Vouvoiement »
retiré de l'écran (la clé `style.vouvoiement` reste en configuration, vouvoiement
par défaut).

### Détail des options examinées

1. **Sommaire + défilement** plutôt que des onglets. Les onglets cachent ce
   qu'on n'a pas encore vu et le bouton « Enregistrer » du pied de modale
   enregistrerait des onglets invisibles.
2. **Corrections de dictée : littérales par défaut.** Aujourd'hui chaque
   correction est une expression régulière sensible à la casse :
   `N.E.E.L => N-EEL` remplace n'importe quels caractères. Proposition :
   remplacement du mot entier, insensible à la casse ; une ligne qui commence
   par `re:` garde toute la puissance des expressions régulières. Changement
   de comportement côté serveur (`stt._apply_corrections`), sans utilisateurs
   à migrer.
3. **Listes à choix** pour verrouillage, dictée, conservation et sauvegarde
   automatique (avec entrée « personnalisé » pour une valeur déjà enregistrée
   hors liste), champs numériques conservés pour seuils et cotation.
4. **Retour aux valeurs recommandées par section** : nouvelle route
   `DELETE /api/config/{section}` (liste blanche : `llm`, `stt`,
   `embeddings`, `style`, `seuils`, `cotation`, `rgpd`, `sauvegarde`,
   `maj` ; jamais `praticien`), appuyée sur `ConfigStore.effacer_section`
   qui existe déjà, tracée dans le journal d'audit. Facultatif : le reste du
   plan tient sans.
5. **Trame et catalogues déplacés** dans « Mes comptes-rendus » et « Mes
   tests », leurs éditeurs inchangés.
6. **« L'assistant me vouvoie »** placé dans « Ma dictée » (c'est là que
   l'assistant pose ses questions), ou supprimé de l'écran si le réglage ne
   vaut pas une ligne.

## Changements par fichier

- **`app/static/index.html`** : bloc `#settingsOverlay` réécrit (sommaire,
  sept sections, `<details>` technique) ; CSS des bulles, pastilles et
  sommaire ; objet `AIDES` ; `fillSettings`/`collectSettings` complétés
  (listes à choix, valeur personnalisée) ; aperçus vivants ; piège de focus
  qui ignore le contenu d'un `<details>` fermé ; Échap à deux temps.
- **`app/main.py`** : `GET /api/config/defauts` ; `DELETE /api/config/{section}`
  (décision 4).
- **`app/stt.py`** : corrections littérales, préfixe `re:` (décision 2).
- **`app/config.py`** : commentaire des corrections mis à jour ; rien d'autre.
- **`README.md`**, **`CHANGELOG.md`** (1.10.0), **`docs/guide-test.md`**
  (étape « Réglez votre cabinet » dans le parcours d'essai),
  **`docs/PROGRESS.md`**.

## Tests

- **`tests/ui/test_parametres_ui.mjs`** (nouveau) :
  - chaque champ `cfg*` de la modale a une bulle et un `aria-describedby` ;
  - la bulle s'épingle au clic, Échap la ferme sans fermer la modale, le
    second Échap ferme la modale ;
  - le bloc technique est fermé à l'ouverture et le piège de focus ne s'y
    arrête pas ;
  - montants de cotation et exemple de seuils recalculés à la frappe ;
  - une valeur hors liste (few_shot_k = 7) reste affichée « personnalisé » et
    repart telle quelle à l'enregistrement ;
  - aller-retour `fillSettings` → `collectSettings` : toute clé affichée est
    renvoyée (garde-fou du « réglage qui s'affiche mais ne se sauvegarde
    pas ») ;
  - liste des modèles : modèle configuré absent → entrée « non installé ».
- **`tests/ui/test_robustesse_ui.mjs`** : focus d'ouverture (désormais
  `cfgPratPrenom`), piège de focus avec `<details>`.
- **`tests/test_api.py`** : `GET /api/config/defauts` (égal à
  `config.DEFAULTS`), `DELETE /api/config/{section}` (section connue →
  surcharge effacée et audit ; inconnue ou `praticien` → 404).
- **`tests/test_unites.py`** : corrections littérales (mot entier, casse),
  préfixe `re:`, expression invalide ignorée.

## Séquencement et estimation

Le **lot A « mise en forme »** est en cours dans l'arbre de travail principal
(`index.html` compris, non commité). Ce plan réécrit le bloc Paramètres du même
fichier : il est réalisé **dans un arbre de travail séparé, sur la branche
`parametres-comprehensibles`**, à fusionner après le commit du lot A. La case
« L'assistant peut mettre en forme » n'est affichée (et renvoyée) que si la clé
`style.mise_en_forme_ia` existe dans la configuration reçue : avant la fusion,
rien n'est envoyé pour cette clé, donc aucun risque de désactiver la mise en
forme par un enregistrement.

| Lot | Contenu | Estimation |
|---|---|---|
| P1 | Structure, sommaire, libellés, bloc technique, bulles et textes, listes à choix, focus et Échap, tests UI | 1,5 à 2 jours |
| P2 | Aperçus vivants (cotation, seuils, signature, dictée), liste des modèles installés, corrections littérales, tests | 1 jour |
| P3 | Défauts exposés, pastille « modifié », retour par section, tests API, docs et CHANGELOG | 0,5 à 1 jour |

## Définition de « fini »

`pytest` + `ruff check .` + suites UI vertes (dont
`tests/ui/test_parametres_ui.mjs`), aucun mot de code dans les libellés
visibles hors bloc technique, CHANGELOG, README et guide de test à jour.
