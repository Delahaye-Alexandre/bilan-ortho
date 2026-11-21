# Journal des modifications

Toutes les évolutions notables de Bilan Ortho, version par version. Les
numéros suivent la [gestion sémantique de version](https://semver.org/lang/fr/) ;
chaque version correspond à un tag git `v<version>` et, depuis la 1.2.0, à un
installeur Windows publié dans les releases.

## Non publié

## 1.15.1 — 2026-11-21

- **L'analyse fonctionne de nouveau avec le modèle compact (qwen3.5:4b)**, celui
  que l'installation propose sur les postes modestes. Ce modèle rend sa réponse
  entre balises de code ; depuis la 1.15.0, elle était rejetée comme
  « illisible » à chaque analyse. Mesuré après correction, même dictée, trois
  passages : 5 à 7 rubriques remplies en 84 à 115 secondes.
- **Deux fenêtres ouvertes sur le même bilan** : enregistrer une rubrique que
  l'autre fenêtre (ou une analyse) vient de modifier ne l'écrase plus. La
  version actuelle est rechargée à la suite de votre texte, à relire avant
  d'enregistrer.
- Le temps écoulé d'une analyse n'est plus relu chaque seconde par les
  lecteurs d'écran.
- **Relecture guidée.** Une barre, toujours visible en haut du compte-rendu,
  dit combien de rubriques restent à relire et lesquelles portent un point à
  vérifier ; « Aller à la suivante » y mène, et Ctrl+Entrée dans une rubrique
  la valide et passe à la suivante. Il fallait parcourir la page à la
  recherche des badges « à valider ». Les statuts s'affichent en clair
  (« validé », « envoyé »).
- **Import de vos bilans de référence** : un PDF numérisé qui porte une mince
  couche de texte (« Numérisé avec… ») passe bien à la reconnaissance de
  caractères au lieu d'être importé vide ; le texte d'un lien dans un document
  Word n'est plus perdu ; les commentaires et notes de bas de page d'un
  document LibreOffice ne se mêlent plus au texte ; les titres d'un fichier
  Markdown sont reconnus sans leurs dièses.

## 1.15.0 — 2026-11-21

Une relecture complète de l'application, du point de vue de l'orthophoniste :
moins d'attente, aucune saisie perdue, un compte-rendu qui dit exactement ce
qui a été validé.

- **Listes numérotées** : une liste interrompue par une ligne vide, un
  commentaire ou une sous-liste à puces reprend sa numérotation (« 2. », « 3. »)
  au lieu de repartir à « 1. », dans l'éditeur comme dans le Word, le PDF et
  le Markdown.
- **L'analyse démarre plus vite.** Le modèle d'IA était déchargé de la mémoire
  pendant chaque dictée et rechargé au moment de « Structurer » (une dizaine de
  secondes, davantage sur un disque lent). Il reste en mémoire vingt minutes
  et se recharge, s'il le faut, pendant que vous relisez votre dictée.
- **Relancer l'analyse ne double plus le texte.** Quand l'application invite à
  relancer (analyse incomplète, passage non rangé), la nouvelle proposition
  remplace celle du passage précédent au lieu de s'y ajouter ; une rubrique
  que vous avez corrigée entre-temps n'est jamais touchée.
- **Paramètres** : fermer la fenêtre (Échap, ✕, clic à côté) avec des
  modifications non enregistrées demande confirmation ; « Enregistrer »
  signale une trame, un catalogue ou une consigne modifiés qui ont leur propre
  bouton.
- Les rubriques « à vérifier » sont nommées en fin d'analyse ; le domaine et le
  type suivent le dossier ouvert ; les champs ont une bordure nettement plus
  lisible ; les boutons de fermeture ont un nom pour les lecteurs d'écran et
  rendent le focus.
- **Saisie des épreuves en série** : après « Ajouter », le nom du test et
  l'échelle restent, le curseur revient sur « Sous-épreuve », et Entrée ajoute
  l'épreuve — il fallait retaper le nom du test et recliquer pour chacune des
  sous-épreuves d'une batterie.
- **Le sélecteur « Patient » suit le dossier ouvert** : resté sur le patient
  précédent, il faisait créer le « + Nouveau bilan » pour quelqu'un d'autre.
- **Enregistrer les Paramètres ne fige plus les valeurs recommandées.**
  Renseigner son nom enregistrait du même coup la valeur AMO, les seuils et le
  vocabulaire intégré comme « personnalisés » : les valeurs des versions
  suivantes n'arrivaient plus.
- Écran de verrouillage : il ne propose plus « Créer le coffre » au premier
  verrouillage de la journée d'installation. Première installation : l'écran
  est utilisable au clavier et ne revient plus toutes les trois secondes après
  « Passer cette étape ». Export : « Préparation du document… » puis
  confirmation du téléchargement.
- **Changer de modèle d'embeddings n'efface plus vos bilans de référence.**
  Le style cessait de s'appliquer sans explication, puis le premier import
  supprimait toute la base. Les références sont désormais réindexées avec le
  nouveau modèle, et l'analyse dit pourquoi le style n'a pas été appliqué.
- **Messages d'erreur de saisie en français** (« Seuil de fragilité : la
  valeur doit être inférieure ou égale à 0 ») au lieu du message technique en
  anglais.
- **Export Word** : format A4 (il sortait au format américain « Letter », le
  PDF en A4) ; un logo en bandeau ne déborde plus de la page ; un caractère
  invisible collé depuis Word ou un PDF (retour à la ligne manuel, saut de
  page) ne bloque plus l'export.
- **Document** : « À l'attention de Madame Durand » ou « Destinataire : CMP de
  Lille » au lieu de « du Dr Madame Durand » ; le titre professionnel garde ses
  sigles sous la signature (« orthophoniste D.E. ») ; « 1er percentile », plus
  de « 10ee percentile » ; drapeau et interprétation séparés par un tiret dans
  le tableau des résultats.
- **Import** d'un fichier texte enregistré par le Bloc-notes : les accents ne
  sont plus supprimés (« Anamnse »), l'UTF-16 est accepté.
- Une rubrique dont la clé de trame contient « / », « ? » ou « # » peut de
  nouveau être enregistrée.
- **L'adresse du moteur d'IA est garantie locale au moment de l'appel.** La
  variable d'environnement `OLLAMA_HOST` était reprise telle quelle : réglée
  sur une autre machine, elle y envoyait la dictée sans aucun refus ; réglée
  sur « 0.0.0.0 » (valeur que la documentation d'Ollama fait poser), elle
  rendait l'IA « injoignable ». Une adresse non locale est désormais ignorée,
  et « 0.0.0.0 » compris comme cette machine.
- **Réduire la durée de conservation ne supprime plus rien en silence.**
  L'écran Paramètres annonce combien de bilans et de fiches partiront à la
  prochaine ouverture et demande confirmation ; à l'ouverture, un bandeau dit
  ce qui a été supprimé. Le même bandeau signale une sauvegarde automatique
  qui échoue (clé USB absente) : elle pouvait échouer des semaines sans que
  rien ne s'affiche.
- **Restauration plus sûre.** Une sauvegarde abîmée au milieu du fichier est
  refusée avant de toucher au coffre (elle le remplaçait par un coffre
  illisible) ; la copie de sécurité prise avant la restauration n'est plus
  effacée dans la foulée quand une seule copie est conservée ; un coffre
  lui-même abîmé n'empêche plus de restaurer une copie saine.
- **Premier lancement interrompu** (coupure, disque plein, antivirus) :
  l'application repropose de créer le coffre, avec confirmation de la
  passphrase, au lieu de « Passphrase incorrecte » à chaque essai.
- Un coffre ouvert par une version plus récente donne un message clair au
  lieu de « erreur serveur » ; l'état de l'application répond même pendant un
  déverrouillage lent (un second clic sur l'icône lançait un second serveur).
- **Transcription de la dictée presque deux fois plus rapide.** La liste de 41
  mots-clés génériques transmise à la reconnaissance vocale doublait le temps
  de calcul. Elle est remplacée par quelques termes d'étalonnage et les noms
  des tests du domaine du bilan ouvert. Mesuré sur une dictée de 88 secondes,
  sans carte graphique : 80 à 100 secondes avant, 45 après, pour un texte aussi
  juste (« l'Alouette », « la BALE », « écart-type »). Votre propre liste
  (⚙️ Paramètres → Ma dictée) passe toujours en premier ; gardez-la courte.
- **Moins de fausses alertes « chiffre absent de la dictée », et une vraie de
  plus.** Les tirets de « ODEDYS-2 », « EVALEO 6-15 », « 3-4 séances » étaient
  lus comme des signes moins : la rédaction fidèle était signalée, et à
  l'inverse un « -2 ET » inventé passait pour dicté dès que « ODEDYS-2 »
  figurait dans la dictée ou au tableau. Un test transcrit d'un seul bloc
  (« EVALEO 615 », « NEEL ») est reconnu comme dicté.
- **Un passage que le modèle range sous une rubrique inconnue n'est plus
  perdu** : son texte est affiché, à copier dans la rubrique voulue. Une
  dictée dont rien n'a été rangé n'est plus effacée comme après un succès.
- **Une dictée longue aboutit toujours.** Sur un poste sans carte graphique,
  transcrire une dictée prend à peu près le temps de la dictée : au-delà du
  délai de verrouillage (15 minutes par défaut), le coffre se verrouillait en
  plein calcul, le texte était jeté et « Réessayer » échouait de la même
  façon. Une transcription, une analyse ou un import en cours suspendent
  désormais le verrouillage d'inactivité, qui repart à la fin.
- **Une dictée ne peut plus atterrir dans le dossier d'un autre patient.**
  Changer de dossier pendant la transcription déposait le texte sous
  l'identité du dossier suivant ; le changement attend la fin de la
  transcription, et un enregistrement en attente de « Réessayer » est signalé
  avant d'être abandonné (comme avant un F5 ou un verrouillage).
- **La fin d'une analyse ne détruit plus de saisie.** Ce qui a été dicté ou
  tapé pendant l'analyse reste dans le champ (seul le texte envoyé en sort) ;
  une rubrique corrigée pendant l'analyse garde votre correction et reçoit à la
  suite ce que l'analyse y a ajouté, au lieu de le masquer puis de l'effacer à
  l'enregistrement ; un bilan supprimé pendant son analyse rend un message
  clair et conserve la dictée.
- **L'alerte « dictée trop longue pour le modèle » s'affiche enfin** : elle
  était calculée par le serveur, jamais montrée.
- **La dictée ne contacte plus Hugging Face à chaque lancement** : le modèle
  déjà installé est chargé depuis le disque, sans réseau. Aucune donnée
  n'était transmise, mais la promesse « seul GitHub » était inexacte.
- **Un écart-type saisi avec un vrai signe moins n'est plus classé « dans la
  norme ».** « −2,1 » (le signe que l'application affiche elle-même, et celui
  des comptes-rendus de logiciels de tests), « –2,1 » (tiret de Word) ou
  « - 2,1 » étaient lus +2,1 : le tableau imprimait « dans la norme » pour un
  déficit sévère. Le signe est reconnu sous toutes ces formes, et un brouillon
  dont un drapeau enregistré contredit la valeur et vos seuils le signale.
- **Un bilan validé dont le contenu change redevient un brouillon.** Après une
  nouvelle analyse, une rubrique retouchée, une épreuve ajoutée ou retirée, un
  en-tête corrigé, le bilan restait « validé » ou « envoyé » : l'export sortait
  sans la mention BROUILLON, texte de l'IA non relu compris. L'application le
  dit et demande de valider de nouveau.
- **Même âge dans le texte et dans l'en-tête.** L'âge transmis au modèle était
  calculé au jour de la saisie, celui du document à la date du bilan : un
  compte-rendu rédigé après la séance pouvait dire « 8 ans » dans le texte et
  « 7 ans et 11 mois » dans l'en-tête.
- **« Marquer validé » vérifie ce qu'il valide.** S'il reste des rubriques « à
  valider » ou signalées, l'application les nomme et vous demande d'attester
  les avoir relues ; elles passent alors « validées ».
- **Bibliothèques embarquées : correctifs de sécurité.** Pillow 13 (traitement
  du logo), pypdf 6.21 (lecture des PDF importés), cryptography 50
  (vérification des mises à jour), certifi et filelock (téléchargement du
  modèle de dictée) : GitHub signalait 89 alertes sur les versions figées en
  septembre. Ces bibliothèques ne lisent que les fichiers que vous importez
  vous-même et les téléchargements de l'application ; le risque concret
  restait limité, mais un logiciel qui traite des données de santé ne garde
  pas de failles connues. Vérifié : même dictée, même texte au mot près avant
  et après ; téléchargement réel du modèle ; tests sous Python 3.11, 3.12 et
  3.13 ; chaque version existe pour Windows.
- **Veille des dépendances remise d'aplomb.** Dependabot s'était mis en pause
  (aucune proposition traitée en 90 jours) et ne proposait pas les montées
  majeures, justement celles qu'exigeaient ces correctifs.
  `scripts/verrouiller-dependances.sh` gagne `--monter <paquet>`, un délai de
  carence de sept jours après publication (une version piégée est en général
  retirée avant) et des plafonds datés et motivés
  (`scripts/plafonds-dependances.txt`) pour les montées majeures que rien
  n'impose. La mise à jour du verrou devient une étape de chaque version.
- **Prompt de structuration allégé** : les consignes répétées (« n'invente
  rien » dite quatre fois, « ne repose pas une question » cinq fois entre le
  prompt et les en-têtes du message, « strictement en JSON » alors que le
  format est déjà imposé) sont dites une seule fois. Mesuré sur qwen2.5:7b,
  même dictée, cinq passages : 1, 1, 1, 1 puis 7 rubriques remplies avant,
  7, 2, 5, 6, 7 après — un compte-rendu complet trois fois sur cinq contre une.
  Un schéma JSON imposé à Ollama a été essayé et écarté (moins complet).
- **Redites signalées** : quand un passage de structuration propose pour une
  rubrique un texte déjà présent pour l'essentiel (même dictée relancée, ou
  modèle qui réécrit l'existant à la suite au lieu de le compléter), la
  rubrique est marquée « à vérifier » avec la mention du doublon. La consigne
  « ne répète pas ce qui figure déjà » n'était garantie par rien : un second
  passage sur la même dictée réécrivait l'objet de la demande à la suite du
  premier (passe réelle du 5 septembre 2026). Rien n'est supprimé : vous
  tranchez à la relecture.
- **Journal du serveur** : les comptes exacts rendus par Ollama à chaque
  structuration (tokens du prompt, tokens générés, motif d'arrêt) sont
  journalisés, et les messages d'information de l'application apparaissent
  enfin dans le journal — ils étaient perdus faute de configuration.
- Nettoyage : le repli qui cherchait un objet JSON « noyé dans du texte » est
  retiré, Ollama garantit un JSON valide en mode `format`.

## 1.14.0 — 2026-09-05

- Documents juridiques consolidés, sources vérifiées le 4 septembre 2026 :
  règlement (UE) 2026/1744 (« omnibus » IA, JO du 24 juillet 2026) intégré à
  l'auto-évaluation AI Act — reports de l'annexe III au 2 décembre 2027 et
  de l'annexe I au 2 août 2028 confirmés, article 4 (maîtrise de l'IA)
  assoupli, qualification inchangée ; notice d'usage alignée ; registre RGPD
  avec les sources CNIL (pas de DPO ni d'AIPD en exercice individuel) ;
  mention d'information complétée (caractère nécessaire des données) et
  rapprochée des exemples de la CNIL.
- Signature de code : `docs/signature-code.md` présente les voies
  vérifiées et leur ordre — rien pour l'instant (avertissements expliqués),
  Certum « Open Source » (49 € en nuage ou 69 € avec carte, au nom de la
  personne, signature locale), SignPath Foundation plus tard (exige une
  réputation vérifiable), Azure écarté (abonnement).
- **Étalonnages** : l'alerte de plausibilité (percentile hors 0-100, note
  sur la mauvaise échelle…) est recalculée par le serveur à chaque lecture du
  bilan et affichée sous l'épreuve concernée — elle n'était rendue qu'au moment
  de la saisie et disparaissait au premier rechargement, alors que le drapeau
  du compte-rendu en dépend toujours.
- **Seuils de drapeaux** : la cohérence sévère ≤ pathologique ≤ fragilité est
  jugée sur la configuration qui sera effectivement appliquée, pas sur le seul
  réglage envoyé — modifier un seuil à la fois pouvait installer un jeu
  incohérent sans un mot (passe réelle du 2026-09-02).
- **Bilans de référence — pseudonymisation** : un prénom en casse mixte
  accolé au patronyme en capitales sur une ligne d'en-tête sans étiquette
  (« DURAND Léa », « Léa DURAND — 7 ans ») est désormais relevé et caviardé
  dans tout le document — il restait en clair. Les titres de rubriques en
  capitales hors du tronc commun (« ANTÉCÉDENTS MÉDICAUX », « PRÉCONISATIONS »)
  et les étiquettes de champ (« HORAIRES : ») ne sont plus remplacés par
  « [NOM] » : l'extrait garde sa structure.
- **Adossement à la dictée** : le seuil d'alerte est plus bas pour le
  diagnostic et le projet thérapeutique, qui s'écrivent dans le vocabulaire
  du clinicien (une conclusion fondée était signalée une fois sur deux), et
  une rubrique de deux phrases est désormais jugée (huit termes au lieu de
  douze).
- **Conservation (RGPD)** : la fiche d'un patient qui n'a plus aucun bilan et
  dépasse le délai de conservation est supprimée à chaque déverrouillage — elle
  ne partait qu'en effet de bord d'une purge de bilans le même jour, et pouvait
  rester des années. Aide du réglage et registre des traitements alignés.
- **Copie pré-migration** : la copie du coffre prise avant un changement de
  schéma est désormais une sauvegarde comme les autres (même dossier, suffixe
  `-avant-migration-vN`) : listée, restaurable depuis les Paramètres, soumise à
  la rotation et couverte par la mention faite aux patients. Rangée jusqu'ici
  à la racine des données sous un autre nom, elle n'était jamais tournée ; la
  copie laissée par les versions précédentes rejoint les sauvegardes au
  premier déverrouillage.
- **Copier le bilan** : quand la copie suit une demande d'enregistrement des
  corrections en cours, le navigateur peut refuser le presse-papiers (le clic
  est « oublié » le temps de lire la confirmation). Les corrections sont bien
  enregistrées et le message invite à cliquer de nouveau — il conseillait de
  copier le texte à la main.
- **Chiffres dictés en ordinaux** : « au cinquième percentile », « au
  vingt-cinquième » sont désormais reconnus comme 5 et 25 dans la dictée. Le
  garde-fou des chiffres signalait « 5 absent de la dictée » sur un percentile
  fidèlement restitué, et lisait 20 dans « vingt-cinquième » (passe réelle du
  5 septembre 2026).

## 1.13.0 — 2026-09-04

Ouverture du dépôt aux orthophonistes : écran de verrouillage et d'accueil dès
l'ouverture, démarrage plus rapide, information des patients et notice d'usage
de l'assistant, guide d'installation et page « vérifiez vous-même que rien ne
sort », build reproductible.

- PDF : les marqueurs de liste (puces, numéros) prennent la police et la
  taille du texte, et les numéros leur point (« 1. ») — un « 1 » de 9 points
  flottait au-dessus de la ligne.
- **Adoption** : guide d'installation pérenne (`docs/installation.md`),
  distinct du protocole d'essai (`docs/guide-test.md`, données fictives,
  trois questions en retour) ; page « Vérifiez vous-même que rien ne sort »
  (`docs/verifier-que-rien-ne-sort.md` : mode avion, bilan complet, Moniteur
  de ressources, ce que le code garantit) ; captures d'écran et compte-rendu
  fictif complet en PDF dans `docs/captures/`, montrés dans le README ; sujets
  GitHub du dépôt renseignés.
- **Durée de dictée bornée côté serveur** : la limite `rgpd.dictee_max_minutes`
  n'arrêtait que le micro du navigateur ; un enregistrement plus long envoyé
  directement à l'API était transcrit. Le serveur la vérifie désormais avant
  la transcription quand le fichier annonce sa durée, après sinon, et ne rend
  jamais le texte d'une dictée trop longue (400 explicite).
- Test des chemins accentués (`tests/test_chemins.py`) : coffre, exports et
  sauvegarde dans un dossier de données avec accents, espaces et apostrophe,
  comme un `%LOCALAPPDATA%` Windows dont le nom de session en porte.
- **Build reproductible** : `requirements-lock.txt` fige désormais toutes les
  dépendances, directes et transitives (51 paquets, marqueurs Linux et
  Windows dans le même fichier), au lieu de 14 dépendances directes qui
  laissaient flotter les briques natives de la dictée ; régénération par
  `scripts/verrouiller-dependances.sh`. L'outillage de la CI (pytest, ruff,
  PyInstaller, OCRmyPDF) est épinglé dans des fichiers `requirements-*.txt`
  surveillés par Dependabot.
- **Écran de verrouillage dès l'ouverture** : la page s'ouvre sur le coffre
  chiffré, avant tout script — l'intérieur de l'application n'apparaît plus
  pendant l'initialisation. Le déverrouillage n'attend plus la vérification
  de l'installation (Ollama, GPU, modèles), qui tourne en arrière-plan.
- **Verrouillage d'inactivité visible aussitôt** : la page apprenait le
  verrouillage au clic suivant, et le dossier restait lisible à l'écran
  entre-temps. Elle consulte désormais l'état à l'échéance annoncée par le
  serveur et au retour de veille ou de l'onglet ; une frappe ou un clic
  signale l'activité (au plus une fois par minute), pour que « inactif »
  veuille dire inactif.
- **Écran d'accueil au démarrage** : le lanceur ouvre aussitôt une fenêtre
  « Ouverture de l'application… » qui bascule sur l'app dès que le serveur
  répond — le navigateur se lance pendant que le serveur démarre, au lieu
  d'après.
- **Démarrage plus rapide** : la détection du GPU (import de ctranslate2,
  nvidia-smi — jusqu'à plusieurs secondes sous Windows) n'est faite qu'une
  fois par session au lieu d'à chaque écran d'installation et chaque
  « Dictée : … ».
- **Information des patients (RGPD art. 13)** : un modèle de mention prêt à
  remettre, avec une version courte pour la salle d'attente
  (`docs/mention-information-patient.md`), et dans le dossier patient une
  case « Mention d'information remise » qui garde la date de la remise (table
  `consentement`, jusqu'ici déclarée et jamais utilisée). Ce n'est pas un
  consentement : la prise en charge n'en exige pas, c'est la trace que
  l'information a été donnée.
- **Notice d'usage de l'assistant** (`docs/notice-usage-ia.md`, règlement IA
  art. 4) : la chaîne étape par étape, ce que l'assistant ne fait pas, ses
  modes d'échec et ce que les vérificateurs n'attrapent pas, les gestes de
  relecture attendus. Citée par l'auto-évaluation AI Act (§ 6.3) ; ses
  références au code sont vérifiées par `tests/test_docs.py`.
- Documents mis à jour : `SECURITY.md` ne cite plus un numéro de version
  (« la dernière release publiée », lien vers la page Releases), dépôt public,
  Dependabot et secret scanning activés ; charte, déclaration MDR et
  auto-évaluation AI Act révisées pour la 1.12.0 ; le README ne renvoie plus
  vers « un DPO / juriste » comme condition d'usage.

## 1.12.0 — 2026-09-04

Cette version achève le plan « mise en forme » : mise en page des documents
et logo (lot B), trame reprise d'un de vos bilans (lot C), gabarit Word du
cabinet (lot D). Les lots A et B des Paramètres compréhensibles étaient dans
la 1.11.0.

Lot D du plan « mise en forme » (`docs/plan-mise-en-forme-2026-09-03.md`) :

- **Mon papier à en-tête (gabarit Word)** : dans ⚙️ Paramètres → Mise en
  page, déposez un document Word de votre cabinet (.docx, ou modèle .dotx,
  converti). Vos comptes-rendus Word en reprennent l'en-tête, le pied de
  page, les marges, la police et les styles de titre ; son texte est ignoré,
  le contenu du bilan prend sa place. Ce que le gabarit ne définit pas est
  complété : titres d'après la couleur et la taille réglées, listes écrites
  en texte, tableau quadrillé, numéros de page dans un pied de page vide si
  le réglage est coché. Le fichier est vérifié (document Word sans macro,
  mise en page d'un bilan d'essai) et rangé dans le coffre chiffré, à part
  de la configuration (`PUT`/`GET`/`DELETE /api/config/gabarit`).
- Case « Mon gabarit porte déjà l'identité du cabinet » : le document ne
  répète pas nom, adresse et numéros sous l'en-tête du gabarit.
- « Exemple Word » télécharge le bilan fictif de l'aperçu en .docx, sur le
  gabarit s'il y en a un, avec les réglages de l'écran
  (`POST /api/config/mise_en_page/apercu?format=docx`). Le PDF et l'aperçu
  gardent les réglages de la section : le gabarit ne s'applique qu'au Word.
- Correction : une liste dans un document sans style de liste ne laisse plus
  un paragraphe vide devant chaque élément.

Lot C du plan « mise en forme » (`docs/plan-mise-en-forme-2026-09-03.md`) :

- **Reprendre la trame d'un de mes bilans** : dans ⚙️ Paramètres → Trame des
  bilans, un bouton lit un de vos comptes-rendus (Word, LibreOffice, PDF,
  texte) et en reprend les intitulés de rubriques, dans l'ordre, dans la liste
  en édition — à vérifier, puis « Enregistrer la trame ». Le document n'est ni
  conservé ni indexé (`POST /api/config/trame/analyse`). Les intitulés
  reconnus du tronc commun gardent leur clé (« Bilan analytique » →
  `epreuves`), les autres reçoivent une clé déduite du titre.
- Après l'import d'un bilan de référence, le compte rendu propose un lien
  « Reprendre sa trame (n rubriques) » qui ouvre l'éditeur avec la même
  proposition ; rien n'est appliqué sans ce clic.
- Les titres stylés (Word, LibreOffice) découpent désormais les extraits de
  référence, même sans mot-clé ; un extrait est retrouvé pour la rubrique de sa
  clé et pour celle qui porte son intitulé, de sorte qu'une trame reprise d'un
  bilan retrouve les extraits de ce bilan.

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
