# Registre des traitements — gabarit (RGPD art. 30)

> À compléter et conserver par le praticien (responsable de traitement).
> Ce gabarit ne vaut pas conseil juridique : faites-le valider par un DPO /
> juriste santé avant tout usage sur de vrais patients, en particulier pour la
> politique de consentement à l'enregistrement vocal.

## 1. Responsable de traitement
- Nom / cabinet : ……
- N° RPPS / ADELI : ……
- Coordonnées : ……

## 2. Traitement : « Aide à la rédaction de bilans orthophoniques »
- **Finalité** : rédaction et conservation des comptes-rendus de bilan.
- **Base légale** : exécution de la mission de soins ; secret médical.
- **Catégories de personnes** : patients (et représentants légaux).
- **Catégories de données** : identité, données de santé (bilan, tests,
  observations), éventuel **enregistrement vocal** (transcrit puis supprimé).
- **Destinataires** : le praticien ; le médecin prescripteur (compte-rendu) ;
  le cas échéant, avec accord, école / MDPH.
- **Sous-traitants** : **aucun** (traitement 100 % local, pas d'hébergeur tiers).
- **Transferts hors UE** : **aucun**.

## 3. Durée de conservation
- Bilans / dossiers de soins : selon les durées applicables aux dossiers de
  soins (à préciser). Paramétrable dans l'app (`rgpd.conservation_jours`).
- **Audio brut** : supprimé après validation du texte (minimisation) —
  `rgpd.audio_purge_apres_validation`.

## 4. Mesures de sécurité (mises en œuvre par l'app)
- **Chiffrement au repos** : base SQLCipher (AES-256), déverrouillage par
  passphrase non stockée.
- **Contrôle d'accès** : passphrase + **verrouillage automatique sur inactivité**
  (`rgpd.verrouillage_inactivite_minutes`).
- **Journalisation** : table `audit_log` (déverrouillages, actions).
- **Réseau** : service lié à `127.0.0.1` ; aucun appel réseau sortant.
- À la charge du praticien : chiffrement du disque (LUKS/BitLocker), sauvegardes
  chiffrées conservées hors du cabinet, antivirus/pare-feu à jour.

## 5. Droits des personnes
Information des patients ; accès, rectification, effacement (fonctions d'export
et de suppression prévues dans l'app).
