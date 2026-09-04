# Registre des traitements — gabarit (RGPD art. 30)

> À compléter et conserver par l'orthophoniste (responsable de traitement).
> Ce gabarit ne vaut pas conseil juridique. Repère utile : un cabinet libéral
> individuel n'a en principe **ni DPO obligatoire** (le traitement des données
> de patients par un professionnel de santé exerçant seul n'est pas un
> traitement « à grande échelle » — considérant 91 du RGPD) **ni AIPD
> systématique** (liste CNIL des traitements dispensés, délibération
> n° 2019-118). Faire relire par un DPO ou un juriste reste un conseil,
> notamment pour l'information sur l'enregistrement vocal — pas une condition
> d'usage. À vérifier pour votre situation (exercice en société, plusieurs
> professionnels, autres traitements).

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
- **Destinataires** : l'orthophoniste ; le médecin prescripteur (compte-rendu) ;
  le cas échéant, avec accord, école / MDPH.
- **Sous-traitants** : **aucun** (traitement 100 % local, pas d'hébergeur tiers).
- **Transferts hors UE** : **aucun**.

## 3. Durée de conservation
- Bilans / dossiers de soins : selon les durées applicables aux dossiers de
  soins (à préciser). Paramétrable dans l'app (`rgpd.conservation_jours`).
- **Audio brut** : supprimé dès la fin de la transcription, sans option ni
  réglage (`app/stt.py::transcribe`). Le fichier transite par le répertoire
  temporaire du système : un arrêt brutal en pleine transcription peut y
  laisser un enregistrement — d'où l'intérêt d'un disque chiffré (§ 4).
- **Sauvegardes chiffrées du coffre** : un dossier supprimé y subsiste jusqu'à
  la rotation des copies (`sauvegarde.retention`, 10 par défaut). Effacement
  différé admis pour les jeux de sauvegarde, à condition de le mentionner ici —
  l'app le rappelle au moment de la suppression.

## 4. Mesures de sécurité (mises en œuvre par l'app)
- **Chiffrement au repos** : base SQLCipher (AES-256), déverrouillage par
  passphrase non stockée.
- **Contrôle d'accès** : passphrase (modifiable, le coffre est alors re-chiffré
  sur place — `app/security.py::changer_passphrase`) + **verrouillage
  automatique sur inactivité** (`rgpd.verrouillage_inactivite_minutes`), y
  compris sans aucune requête.
- **Journalisation** : table `audit_log` (déverrouillages, actions).
- **Réseau** : service lié à `127.0.0.1` ; aucun appel réseau sortant dans le
  traitement des données. Seules exceptions, hors traitement et toujours vers
  GitHub (`app/maj.py`) : la vérification de mise à jour — un GET vers l'API
  GitHub Releases, au plus une fois par jour au démarrage (réglage activé par
  défaut, annoncé une fois à l'utilisateur, désactivable) ou à la demande — et,
  uniquement quand l'utilisateur clique « Installer maintenant », le
  téléchargement de l'installeur et de ses empreintes signées. Aucune donnée
  personnelle n'est transmise ; comme pour toute connexion, l'adresse IP du
  poste est visible de GitHub. Avant l'installation, une sauvegarde chiffrée du
  coffre est créée et la signature de l'éditeur est vérifiée.
- À la charge de l'orthophoniste : chiffrement du disque (LUKS/BitLocker), sauvegardes
  chiffrées conservées hors du cabinet, antivirus/pare-feu à jour.

## 5. Droits des personnes
Information des patients : un modèle de mention prêt à remettre (articles 12
et 13), avec une version courte pour la salle d'attente, est fourni dans
`docs/mention-information-patient.md` ; l'app garde par dossier la date à
laquelle la mention a été remise (case « Mention d'information remise » du
patient, `app/patient.py::set_information`, table `consentement`). Accès,
rectification, effacement (fonctions d'export et de suppression prévues dans
l'app). La suppression d'un patient emporte ses
bilans, épreuves, prescriptions, dictées et les extraits de style qui lui sont
rattachés (`app/patient.py::delete`).
