# Signature des releases et signature de code Windows

Deux mécanismes distincts protègent les mises à jour. Le premier est en
place et obligatoire ; le second est facultatif et payant.

## 1. Signature Ed25519 des releases (chaîne de confiance de l'app)

À chaque tag `v*`, la CI publie trois fichiers : l'installeur
`BilanOrtho-Setup-x.y.z.exe`, `SHA256SUMS` (son empreinte) et
`SHA256SUMS.sig` (la signature Ed25519 de ce fichier). Avant d'installer une
mise à jour en un clic, l'application (`app/maj.py`) vérifie la signature
avec la clé publique embarquée (`CLE_PUBLIQUE_RELEASES`), puis l'empreinte
de l'installeur téléchargé. Un fichier qui échoue à l'un des deux contrôles
est effacé, jamais exécuté. Même le compte GitHub compromis ne permet pas
de pousser une mise à jour aux postes installés : il faudrait la clé privée.

**Où vit la clé privée.** Uniquement :

- dans le secret GitHub `BILAN_ORTHO_CLE_PRIVEE` du dépôt (graine de 32
  octets en base64) ;
- dans la copie de secours du mainteneur, hors dépôt :
  `~/.local/share/bilan-ortho/cles/releases-ed25519.priv` (droits 600).
  À mettre aussi dans un gestionnaire de mots de passe. **Perdue, aucune
  nouvelle version ne pourra plus s'installer en un clic** sur les postes
  existants (le téléchargement manuel restera possible).

**Rotation.** Publier d'abord une version qui embarque la *nouvelle* clé
publique, signée avec l'*ancienne* clé privée ; puis remplacer le secret.
Les postes passent par cette version intermédiaire.

**Un fork** sans clé : la CI refuse de publier une release sur tag tant que
le secret est absent ; un fork peut générer sa propre paire et remplacer
`CLE_PUBLIQUE_RELEASES`.

Générer une paire (le script imprime la clé publique à coller dans
`app/maj.py`) :

```python
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

k = Ed25519PrivateKey.generate()
seed = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                       serialization.NoEncryption())
pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
print("PRIVEE (secret GitHub) :", base64.b64encode(seed).decode())
print("PUBLIQUE (app/maj.py)  :", base64.b64encode(pub).decode())
```

Poser le secret : `gh secret set BILAN_ORTHO_CLE_PRIVEE < releases-ed25519.priv`.

## 2. Signature de code Windows (Authenticode) — facultative

Sans elle, Windows affiche deux avertissements à l'installation **manuelle**
(« fichier pas fréquemment téléchargé », « Windows a protégé votre
ordinateur »). La mise à jour en un clic depuis l'app ne les déclenche pas,
mais la première installation, si. Une signature identifie l'éditeur et
laisse la réputation SmartScreen s'accumuler d'une version à l'autre ; même
signé, un tout nouveau fichier peut encore déclencher l'avertissement le
temps que quelques installations réussies construisent cette réputation.

Trois voies, vérifiées le 4 septembre 2026. Le projet est gratuit et ne veut
pas d'abonnement ; aucune n'est engagée à ce jour, l'ordre ci-dessous est
celui du rendement.

### 2.0 Pour l'instant : pas de signature, et l'expliquer

Les avertissements sont décrits pas à pas dans `docs/installation.md` et
dans les notes de release ; une fois installée, l'application se met à jour
d'elle-même sans les redéclencher. Pour un cercle d'amies orthophonistes qui
reçoivent le lien de la main du responsable du projet, c'est acceptable.
Revoir la question si les avertissements font renoncer quelqu'un.

### 2.1 Certum « Open Source » — quelques dizaines d'euros, au nom de la personne

Certum (Asseco, Pologne) vend un certificat de signature de code réservé aux
personnes qui publient des logiciels libres ou gratuits, vérifié le
4 septembre 2026 sur shop.certum.eu :

- **« Open Source Code Signing in the Cloud »** : 49 € la première fois,
  sans matériel (service SimplySign, application sur l'ordinateur et code à
  usage unique sur le téléphone à chaque session de signature) ;
- **« Open Source Code Signing — set »** : 69 € avec carte à puce et
  lecteur (plus port), renouvellement de l'ordre de 29 € par an ;
- vérification d'identité par vidéo (IDNow : pièce d'identité), justificatif
  de domicile, et un court dossier décrivant le projet (lien du dépôt,
  licence) ; obtention en quelques jours d'après les retours publiés.

Le certificat est délivré au nom de la personne (validation OV) : il fait
disparaître « Éditeur inconnu » et laisse la réputation SmartScreen
s'accumuler sur le certificat d'une version à l'autre, ce qu'un fichier non
signé ne peut jamais faire. Limite : la signature se fait sur le poste du
responsable (carte ou SimplySign), pas dans la CI. Le flux prévu : la CI
construit l'installeur comme aujourd'hui ; un script local le signe
(`signtool` du SDK Windows, horodatage), recalcule `SHA256SUMS`, le signe
avec la clé Ed25519 locale (§ 1) et remplace les trois fichiers de la
release. Une dizaine de minutes par version, à écrire le jour où le
certificat existe.

### 2.2 SignPath Foundation — gratuit, mais pas encore

La fondation SignPath signe gratuitement les projets libres, mais ses
conditions (signpath.org/terms.html) précisent : « we cannot sign binaries
based on source code that nobody knows. For executable programs that may be
downloaded and executed based on our signature, we require a certain
verifiable reputation », et la décision reste la leur, sans recours. Un
projet sans utilisateurs connus n'y a pas sa place aujourd'hui. À retenter
quand Bilan Ortho aura des utilisatrices visibles (retours publics, étoiles,
téléchargements) ; le reste des conditions est déjà rempli (AGPL, build
automatisé par GitHub Actions) ou facile (double authentification, politique
de signature publiée sur le README, approbation manuelle par version, action
GitHub `signpath/github-action-submit-signing-request`).

### 2.3 Azure Artifact Signing (ex-Trusted Signing) — abonnement

Environ 10 $ par mois (offre Basic, 5 000 signatures), ouvert aux
développeurs individuels après validation d'identité (Microsoft Entra
Verified ID). Les étapes « Signature Authenticode » de la CI sont déjà
écrites pour cette voie et s'activent d'elles-mêmes dès que les six secrets
`AZURE_*` existent ; elles restent en place, inactives. Écarté le
4 septembre 2026 : pas d'abonnement.

### Étapes Azure (conservées, inactives)

1. **Azure** : créer un abonnement (portal.azure.com), puis une ressource
   *Artifact Signing* dans une région européenne.
2. **Validation d'identité** : dans la ressource, *Identity validation* →
   individu (pièce d'identité).
3. **Profil de certificat** : *Certificate profiles* → *Public Trust*, lié
   à l'identité validée.
4. **Identité pour la CI** : Microsoft Entra ID → *App registrations* →
   secret client, rôle *Trusted Signing Certificate Profile Signer* sur la
   ressource.
5. **Secrets GitHub** : `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`,
   `AZURE_CLIENT_SECRET`, `AZURE_SIGNING_ENDPOINT`, `AZURE_SIGNING_ACCOUNT`,
   `AZURE_SIGNING_PROFILE`.
6. Pousser un tag : la release suivante est signée.
