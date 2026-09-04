# Politique de sécurité

> **EN — Security policy:** report vulnerabilities privately to alexandre-delahaye@outlook.fr or via GitHub Security Advisories; do not open a public issue. Only the latest release is supported.

## Versions supportées

Seule la **dernière release** publiée est supportée : celle que présente la page [Releases](https://github.com/Delahaye-Alexandre/bilan-ortho/releases/latest), et que l'application propose d'installer d'elle-même (⚙️ Paramètres → Sécurité et sauvegardes → Mises à jour). Les versions antérieures ne reçoivent pas de correctifs : mettez à jour avant de signaler un problème.

| Version | Supportée |
|---|---|
| Dernière release publiée | Oui |
| Versions antérieures | Non |

## Signaler une vulnérabilité

- **N'ouvrez pas d'issue publique** pour une faille de sécurité.
- Écrivez en privé à **alexandre-delahaye@outlook.fr**, ou utilisez **GitHub Security Advisories** (« Report a vulnerability » dans l'onglet Security du dépôt).
- Décrivez si possible : version concernée, étapes de reproduction, impact estimé.
- **Accusé de réception sous 7 jours.**

## Engagement de correction

- **Vulnérabilités critiques : correctif visé sous 30 jours.** C'est un engagement propre au projet, non une exigence réglementaire chiffrée ; la CNIL recommande, elle, d'appliquer les correctifs de sécurité critiques sans délai — ces 30 jours sont donc un plafond, pas une cible.
- Le reste est traité en **best effort**, et ce terme est assumé : le projet est maintenu bénévolement, avec un **tri mensuel des issues**. Ce rythme est annoncé honnêtement plutôt que promis puis non tenu.

## Périmètre et modèle de menace

L'application fonctionne **100 % en local** : serveur lié à `127.0.0.1` uniquement, protégé par `TrustedHostMiddleware` (hôtes autorisés : `127.0.0.1`, `localhost`), données chiffrées dans une base SQLCipher unique dont la passphrase n'est jamais écrite sur disque.

En trois points :

1. **Couvert** : un poste de travail individuel — pas d'exposition réseau (loopback seul, protection anti-DNS-rebinding, requêtes modifiantes refusées depuis une page tierce), aucune télémétrie, base et sauvegardes chiffrées, mémoire des pages déchiffrées effacée à la libération (`cipher_memory_security` — hors Windows, où la distribution SQLCipher utilisée ne le supporte pas), verrouillage automatique après inactivité y compris sans requête, passphrases prévisibles refusées à la création. Aucune donnée patient n'est transmise en ligne : les hôtes LLM et embeddings sont contraints à la boucle locale par validation de la configuration (`app/models.py`). Seul le téléchargement initial des modèles (Ollama, dictée) nécessite une connexion internet, sans qu'aucune donnée patient n'y transite.
2. **Non couvert** : la compromission du poste lui-même (malware, accès physique, session ouverte) — si la machine est compromise pendant que le coffre est déverrouillé, le chiffrement ne protège plus.
3. **Non couvert** : l'oubli de la passphrase — il n'existe **aucun mécanisme de récupération** ; sans passphrase, les données sont définitivement irrécupérables. C'est un choix de conception, pas un oubli.
4. **À la charge de la personne qui importe** : l'OCR d'un PDF scanné passe par Ghostscript et Tesseract (OCRmyPDF), la plus grande surface d'analyse de fichiers du produit. N'importez comme bilans de référence que des documents que vous avez produits ou reçus d'une source de confiance.

## Mises à jour de dépendances

- Les versions sont figées dans `requirements-lock.txt`, utilisé par la CI et le build (surveillé par Dependabot).
- La **CI s'exécute sur chaque pull request** (lint, tests Python multi-versions et multi-OS, tests UI).
- **Dependabot est activé** (`.github/dependabot.yml` pour les mises à jour, alertes de vulnérabilité au niveau du dépôt) : ses pull requests passent par la même CI. Le **secret scanning** de GitHub est activé sur le dépôt, avec blocage des pushes qui contiendraient un secret.

## Remerciements

Merci aux personnes qui prennent le temps de signaler une vulnérabilité de façon responsable : ce projet manipule des données de santé, et chaque signalement privé protège directement les praticiens et praticiennes qui l'utilisent, ainsi que leurs patients et patientes. Sauf demande contraire, les personnes à l'origine d'un signalement seront créditées dans les notes de version du correctif.
