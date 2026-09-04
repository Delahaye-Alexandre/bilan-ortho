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

Trois voies, vérifiées le 4 septembre 2026. Le projet ne voulant pas
d'abonnement, la première est celle retenue.

### 2.1 SignPath Foundation — gratuit pour les projets libres (voie retenue)

La fondation SignPath signe gratuitement les binaires des projets open
source qui remplissent ses conditions (signpath.org/terms.html) :

- licence approuvée OSI, sans composant propriétaire ni double licence
  commerciale — Bilan Ortho est sous AGPL v3 ;
- projet activement maintenu et déjà publié sous la forme à signer ; sa
  fonctionnalité décrite sur la page de téléchargement ;
- binaire issu d'un build automatisé depuis les sources — c'est le cas
  (GitHub Actions, `dist/BilanOrtho`, installeur Inno) ;
- authentification à deux facteurs pour toute l'équipe, sur SignPath et sur
  GitHub ; rôles déclarés (auteurs, relecteurs, approbateurs — une seule
  personne peut tenir les trois) ;
- une **politique de signature** publiée sur la page d'accueil du projet
  (README), sous ce nom, qui indique que les binaires sont signés par la
  fondation, qui décide d'une signature et que le logiciel n'envoie aucune
  donnée ;
- chaque release est approuvée à la main avant signature.

Mise en place, une fois : candidature sur signpath.org (« Apply »), au nom du
responsable du projet, avec le lien du dépôt ; à l'acceptation, la fondation
fournit une organisation SignPath et un projet ; la CI soumet alors le
binaire et l'installeur par l'action GitHub `signpath/github-action-submit-signing-request`
(secret d'API SignPath dans le dépôt), attend l'approbation et récupère les
fichiers signés — l'étape à ajouter dans `build-windows`, à la place des
étapes Azure ci-dessous. Coût : aucun.

### 2.2 Certum — certificat « Open Source » à bas prix

Certum (Asseco) vend un certificat de signature de code réservé aux
développeurs de logiciels libres, de l'ordre de quelques dizaines d'euros
la première année (carte à puce ou service en nuage SimplySign, validité
limitée à 459 jours depuis février 2026). Le certificat est au nom de la
personne ; la CI signe avec `signtool` ou `osslsigncode`. Une voie de repli
si la candidature SignPath n'aboutit pas.

### 2.3 Azure Artifact Signing (ex-Trusted Signing) — abonnement

Environ 10 $ par mois (offre Basic, 5 000 signatures), ouvert aux
développeurs individuels après validation d'identité (Microsoft Entra
Verified ID). Les étapes « Signature Authenticode » de la CI sont déjà
écrites pour cette voie et s'activent d'elles-mêmes dès que les six secrets
`AZURE_*` existent (Settings → Secrets and variables → Actions) ; elles
restent en place, inactives, au cas où. Écarté le 4 septembre 2026 : le
projet est gratuit et ne veut pas d'abonnement.

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
