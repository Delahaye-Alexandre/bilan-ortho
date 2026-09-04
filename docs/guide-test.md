# Bilan Ortho — protocole d'essai (version test)

Merci de tester Bilan Ortho ! C'est un assistant de rédaction de bilans
orthophoniques qui fonctionne **entièrement sur votre ordinateur** : aucune
donnée ne part sur internet, tout est chiffré sur votre machine.

> ⚠️ **Version de test.** Pendant cette phase, travaillez avec des **données
> fictives** (patients inventés) — pas de vrais dossiers patients.

## Avant de commencer

Installez l'application en suivant `installation.md` : prérequis, installeur,
avertissements de Windows (normaux : application non signée), premier
lancement et téléchargement des modèles d'IA. Comptez 15 à 30 minutes de
téléchargements la première fois ; ensuite tout fonctionne hors ligne — vous
pouvez d'ailleurs le vérifier vous-même (`verifier-que-rien-ne-sort.md`).

## 3. Parcours d'essai suggéré (15 min)

1. Bouton **👤** : créez un patient **fictif** (nom inventé, date de
   naissance réelle plausible — elle sert au calcul de l'âge).
2. Choisissez un domaine (ex. Langage écrit) → **+ Nouveau bilan**.
3. **🎙️ Dictez** naturellement, comme si vous racontiez le dossier à voix
   haute : anamnèse, ce que vous avez observé, les tests passés, les scores…
   À la première dictée, la fenêtre demande l'accès au micro : cliquez
   **« Autoriser »**. (Vous pouvez aussi taper votre texte au clavier.)
4. **➡️ Structurer** : l'assistant répartit vos propos dans la trame et vous
   pose des **questions** quand il manque quelque chose — répondez-y.
5. Saisissez une épreuve dans **🧪 Épreuves & scores** (le drapeau
   norme/pathologique se calcule seul).
6. **Relisez, corrigez, validez** chaque rubrique — c'est vous qui décidez,
   l'IA ne fait que proposer. Mettez en forme si besoin (gras, souligné,
   listes : barre au-dessus de chaque rubrique, ou Ctrl+B / Ctrl+I / Ctrl+U) ;
   vous pouvez aussi coller un passage depuis Word, sa mise en forme est
   conservée.
7. **⚙️ Paramètres → Mon cabinet** : renseignez votre identité
   professionnelle ; l'aperçu montre la signature qui sortira sur le document.
   Survolez un bouton ⓘ : chaque réglage dit à quoi il sert et quelle valeur
   est recommandée. Le bloc « Réglages techniques », en bas, peut rester fermé.
   Dans **Mise en page de mes documents**, choisissez police, marges, couleur
   des titres, numérotation, et déposez votre logo (PNG ou JPEG) : l'aperçu
   d'un bilan fictif se met à jour sous les réglages avant d'enregistrer.
   Si vous avez un papier à en-tête Word, déposez-le comme gabarit :
   « Exemple Word » télécharge un bilan fictif mis en page dessus, à ouvrir
   dans Word ; cochez « porte déjà l'identité du cabinet » si votre en-tête
   indique déjà vos coordonnées.
8. **€ Coter**, **⬇ Word**, puis « Marquer validé ».
9. Optionnel : importez un de vos bilans **anonymisé** dans « Mes bilans de
   référence » — les prochaines rédactions imiteront votre style, y compris
   ce que vous mettez en gras ou en liste (fichiers Word). Le compte rendu de
   l'import propose « Reprendre sa trame » : vos propres rubriques, dans
   votre ordre, deviennent la trame des prochains bilans après vérification
   (aussi depuis ⚙️ Paramètres → Trame des bilans, sans importer).

## Ce que nous attendons de vous

Après l'essai, trois questions, par courriel, en quelques lignes chacune :

1. Le compte-rendu produit ressemble-t-il à ce que vous auriez écrit ? Où
   s'en écarte-t-il ?
2. Qu'est-ce qui vous a fait perdre du temps, ou que vous n'avez pas compris ?
3. Que manque-t-il pour l'utiliser sur de vrais bilans ?

Une capture d'écran vaut souvent mieux qu'une description.

## En cas de problème

Envoyez à Alexandre (**alexandre-delahaye@outlook.fr**) :
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

Confidentialité, responsabilité, désinstallation : section « Ce qu'il faut
savoir » de `installation.md`. En résumé : tout reste chiffré sur votre
machine, l'audio des dictées est supprimé dès la transcription, l'outil ne pose
aucun diagnostic et vous restez entièrement responsable du contenu validé.
