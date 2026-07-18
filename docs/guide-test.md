# Bilan Ortho — guide d'installation (version test)

Merci de tester Bilan Ortho ! C'est un assistant de rédaction de bilans
orthophoniques qui fonctionne **entièrement sur votre ordinateur** : aucune
donnée ne part sur internet, tout est chiffré sur votre machine.

> ⚠️ **Version de test.** Pendant cette phase, travaillez avec des **données
> fictives** (patients inventés) — pas de vrais dossiers patients.

## Prérequis

- Windows 10 ou 11
- 8 Go de RAM minimum (16 Go recommandés : l'assistant sera plus pertinent)
- ~10 Go d'espace disque libre
- Une connexion internet **pour l'installation uniquement** (téléchargement
  des modèles d'IA ; ensuite tout fonctionne hors ligne)
- Un micro (celui du portable suffit) pour la dictée

## 1. Installer l'application

1. Téléchargez `BilanOrtho-Setup-x.y.z.exe` depuis la page des
   téléchargements — <https://github.com/Delahaye-Alexandre/bilan-ortho/releases/latest> —
   ou depuis le lien qu'Alexandre vous a envoyé.
2. Double-cliquez. **Windows affichera un avertissement bleu « Windows a
   protégé votre ordinateur »** : c'est normal — l'application n'est pas
   encore « signée » auprès de Microsoft (procédure payante), pas dangereuse.
   Cliquez sur **« Informations complémentaires »** puis **« Exécuter quand
   même »**.
3. L'installation ne demande aucun droit administrateur. Elle télécharge et
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
irrécupérable** (personne, pas même Alexandre, ne peut la retrouver).

À noter : à la **première dictée**, le modèle de reconnaissance vocale
(~1,5 Go) se télécharge aussi — une seule fois.

## 3. Parcours d'essai suggéré (15 min)

1. Bouton **👤** : créez un patient **fictif** (nom inventé, date de
   naissance réelle plausible — elle sert au calcul de l'âge).
2. Choisissez un domaine (ex. Langage écrit) → **+ Nouveau bilan**.
3. **🎙️ Dictez** naturellement, comme si vous racontiez le dossier à voix
   haute : anamnèse, ce que vous avez observé, les tests passés, les scores…
4. **➡️ Structurer** : l'assistant répartit vos propos dans la trame et vous
   pose des **questions** quand il manque quelque chose — répondez-y.
5. Saisissez une épreuve dans **🧪 Épreuves & scores** (le drapeau
   norme/pathologique se calcule seul).
6. **Relisez, corrigez, validez** chaque rubrique — c'est vous qui décidez,
   l'IA ne fait que proposer.
7. **€ Coter**, **⬇ Word**, puis « Marquer validé ».
8. Optionnel : importez un de vos bilans **anonymisé** dans « Mes bilans de
   référence » — les prochaines rédactions imiteront votre style.

## En cas de problème

Envoyez à Alexandre :
1. Ce que vous faisiez + ce qui s'est passé (capture d'écran si possible) ;
2. Le fichier `serveur.log` situé dans le dossier
   `%LOCALAPPDATA%\bilan-ortho` (tapez ce chemin dans la barre de
   l'explorateur Windows). Il ne contient pas le contenu de vos bilans.

Si l'application ne s'ouvre pas : vérifiez qu'Ollama tourne (icône lama près
de l'horloge), puis relancez Bilan Ortho.

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
