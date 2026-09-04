# Installer Bilan Ortho (Windows)

Bilan Ortho est un assistant de rédaction de bilans orthophoniques qui
fonctionne **entièrement sur votre ordinateur** : aucune donnée ne part sur
internet, tout est chiffré sur votre machine. Ce guide couvre l'installation,
le premier lancement, les mises à jour et les problèmes courants. Pour un
parcours d'essai guidé, voir `guide-test.md` ; pour vérifier vous-même que
rien ne sort de l'ordinateur, `verifier-que-rien-ne-sort.md`.

## Prérequis

- Windows 10 ou 11
- 8 Go de RAM minimum (16 Go recommandés : l'assistant sera plus pertinent)
- ~10 Go d'espace disque libre
- Une connexion internet **pour l'installation et la toute première dictée**
  (téléchargement des modèles d'IA ; ensuite tout fonctionne hors ligne)
- Un micro (celui du portable suffit) pour la dictée

## 1. Installer l'application

1. Téléchargez `BilanOrtho-Setup-x.y.z.exe` depuis la page des
   téléchargements — <https://github.com/Delahaye-Alexandre/bilan-ortho/releases/latest>.
   Sur la page, prenez bien le
   fichier `.exe` de la section « Assets » (pas « Source code », qui n'est
   que le code du logiciel).
2. Votre navigateur peut afficher un avertissement du type « ce fichier
   n'est pas fréquemment téléchargé » : c'est normal — l'application est
   récente et n'est pas encore « signée » auprès de Microsoft (procédure
   payante), pas dangereuse. Cliquez sur les **« ⋯ »** en face du fichier
   téléchargé, puis **« Conserver »** et, si l'écran suivant s'affiche,
   « Afficher plus » → **« Conserver quand même »**.
3. Double-cliquez. **Windows affichera un avertissement bleu « Windows a
   protégé votre ordinateur »** : même raison, toujours pas dangereux.
   Cliquez sur **« Informations complémentaires »** puis **« Exécuter quand
   même »**.
4. L'installation ne demande aucun droit administrateur. Elle télécharge et
   installe aussi automatiquement le moteur d'IA local (**Ollama**, ~1 Go) —
   patientez. Une icône « Bilan Ortho » apparaît sur le Bureau.

## 2. Premier lancement (une seule fois, ~15-30 min de téléchargements)

Au premier double-clic, la fenêtre Bilan Ortho s'ouvre sur l'écran
**« 🚀 Première installation »** qui vous guide :

1. **Moteur Ollama** : normalement déjà installé par l'installeur (✅). S'il
   est marqué absent (installation faite hors ligne), cliquez « Télécharger
   Ollama », installez-le, puis « ↻ Revérifier ».
2. **Modèles d'IA** : l'application propose automatiquement le modèle adapté
   à votre machine. Cliquez « ⬇ Télécharger les modèles » et patientez
   (3 à 6 Go — la barre de progression vous accompagne).
3. Cliquez « Continuer → ».

Ensuite, créez la **passphrase de votre coffre** (12 caractères minimum) :
elle chiffre toutes vos données. **Notez-la précieusement : elle est
irrécupérable** (personne ne peut la retrouver, l'auteur du logiciel
non plus).

À noter : à la **première dictée**, le modèle de reconnaissance vocale
(~1,5 Go) se télécharge aussi — une seule fois.

## Mettre à jour

L'application vérifie d'elle-même, au plus une fois par jour, si une nouvelle
version existe (elle vous le dit la première fois, et vous pouvez désactiver ce
comportement dans ⚙️ Paramètres → Mises à jour). Quand un bandeau annonce une
version, dépliez « Ce qui change » puis cliquez **« Installer maintenant »** :
une sauvegarde de votre coffre est créée, l'installeur est téléchargé et
vérifié (signature de l'éditeur, empreinte), l'application se ferme, s'installe
et redémarre seule — environ une minute, vos données sont préservées. Enregistrez
votre travail avant. « Plus tard » remet ça à une prochaine fois, « Ignorer cette
version » n'en parle plus au démarrage.

Sur une version antérieure à la 1.10.0, ou depuis un dépôt cloné, la mise à
jour reste manuelle : téléchargez l'installeur depuis la page des versions et
lancez-le par-dessus l'existant.

## En cas de problème

Écrivez à **alexandre-delahaye@outlook.fr** ou ouvrez une issue sur GitHub
(<https://github.com/Delahaye-Alexandre/bilan-ortho/issues>), avec :
1. Ce que vous faisiez + ce qui s'est passé (capture d'écran si possible) ;
2. Le fichier `serveur.log` situé dans le dossier
   `%LOCALAPPDATA%\bilan-ortho` (tapez ce chemin dans la barre de
   l'explorateur Windows). Il ne contient pas le contenu de vos bilans.

Si l'application ne s'ouvre pas : vérifiez qu'Ollama tourne (icône lama près
de l'horloge), puis relancez Bilan Ortho.

Si la dictée affiche « Micro refusé ou indisponible » : l'accès au micro a
été bloqué pour la fenêtre. Cliquez sur l'icône de réglages (ou le cadenas)
dans la barre de titre → « Autorisations » → « Micro » → « Autoriser », puis
relancez la dictée. En attendant, vous pouvez toujours taper votre texte.

## Ce qu'il faut savoir

- **Confidentialité** : tout est chiffré (AES-256) et reste sur votre
  machine ; l'application se verrouille seule après 15 min d'inactivité ;
  l'audio des dictées est supprimé dès la transcription ; une sauvegarde
  chiffrée est faite automatiquement chaque semaine.
- **Responsabilité** : l'outil est une aide à la rédaction — il ne pose
  aucun diagnostic ; vous restez entièrement responsable du contenu validé.
- **Désinstallation** : via les Paramètres Windows, comme toute application.
  Vos données (coffre chiffré) sont conservées dans
  `%LOCALAPPDATA%\bilan-ortho` — supprimez ce dossier pour effacer vos
  données. Le moteur d'IA est installé à part : pour le retirer aussi,
  désinstallez « Ollama » (Paramètres Windows) et supprimez le dossier de
  ses modèles (`%USERPROFILE%\.ollama`).
- **Ce que l'assistant fait et ne fait pas**, et comment il se trompe :
  `notice-usage-ia.md`. **Vos patients** : la mention d'information à leur
  remettre est dans `mention-information-patient.md`.
