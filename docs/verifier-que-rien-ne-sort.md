# Vérifiez vous-même que rien ne sort de votre ordinateur

La promesse centrale de Bilan Ortho — vos dictées, vos patients et vos
comptes-rendus ne quittent pas votre machine — se vérifie sans compétence
technique : coupez la connexion, faites un bilan complet, tout fonctionne.
Voici comment, ce que vous pouvez observer, et ce que le code garantit.

## 1. Le test, en dix minutes

1. Attendez la fin de la première installation : les modèles d'IA et de
   dictée sont téléchargés quand une première dictée a fonctionné.
2. Activez le **mode avion**, ou coupez le Wi-Fi et débranchez le câble
   réseau.
3. Ouvrez Bilan Ortho, déverrouillez le coffre, créez un patient fictif,
   dictez, structurez, répondez aux questions de l'assistant, saisissez une
   épreuve, cotez, exportez en Word et en PDF, validez.
4. Tout fonctionne. Les seules actions qui échouent hors ligne : télécharger
   un modèle, et vérifier s'il existe une nouvelle version (annoncée une
   fois, désactivable dans ⚙️ Paramètres → Mises à jour).
5. Rallumez la connexion : rien n'est « envoyé en différé ». L'application
   n'a ni file d'attente réseau, ni compte, ni télémétrie.

## 2. Pour aller plus loin : observer le réseau

- **Moniteur de ressources de Windows** (Ctrl+Maj+Échap → Performance →
  Ouvrir le Moniteur de ressources → onglet Réseau) : pendant un bilan,
  `BilanOrtho.exe` et `ollama.exe` n'échangent qu'avec l'adresse `127.0.0.1`,
  c'est-à-dire l'ordinateur lui-même.
- **Pare-feu Windows** : ajoutez une règle sortante qui bloque `BilanOrtho.exe`
  et `ollama.exe`. L'application continue de fonctionner à l'identique.

## 3. Ce que le code garantit

Le code est public (licence AGPL) : ce qui suit se lit dans le dépôt.

- Le serveur n'écoute que sur `127.0.0.1` (`lanceur.py`, `run.sh`) et
  refuse les requêtes qui ne viennent pas de la page locale (`app/main.py`,
  hôtes autorisés et protection anti-CSRF).
- Les adresses du modèle de langage et des embeddings sont contraintes à la
  boucle locale par la validation de la configuration
  (`app/config.py::hote_est_local`) ; un modèle Ollama « cloud », exécuté
  chez ollama.com, est refusé (`app/llm.py::ModeleCloud`).
- La dictée est transcrite sur place et l'audio supprimé aussitôt
  (`app/stt.py::transcribe`).
- Le seul trafic sortant de l'application : la vérification de mise à jour
  et, sur votre clic, le téléchargement de l'installeur, vers GitHub
  (`app/maj.py::verifier`), sans aucune donnée personnelle. Les modèles
  d'IA sont téléchargés une fois, à l'installation, par Ollama et par le
  moteur de dictée.

## 4. Ce que ce test ne prouve pas

Qu'un ordinateur déjà compromis (logiciel malveillant, session ouverte) ne
puisse rien lire pendant que le coffre est déverrouillé, ni que le disque
lui-même soit chiffré : voir `../SECURITY.md` (modèle de menace) et le
registre RGPD (`RGPD-registre-traitements.md`, mesures à votre charge).
