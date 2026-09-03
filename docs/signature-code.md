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
mais la première installation, si. La signature de code les fait
disparaître et identifie l'éditeur.

Le service retenu est **Azure Artifact Signing** (anciennement Trusted
Signing) : environ 10 $ par mois, ouvert aux travailleurs indépendants de
l'UE depuis 2026, sans certificat à acheter ni à stocker. La CI est déjà
prête : les étapes « Signature Authenticode » s'activent d'elles-mêmes dès
que les secrets existent, et signent le binaire puis l'installeur.

### Mise en place (une fois)

1. **Azure** : créer un abonnement (portal.azure.com), puis une ressource
   *Artifact Signing account* (région Europe de l'Ouest, offre Basic).
2. **Validation d'identité** : dans la ressource, *Identity validation* →
   *Individual* (travailleur indépendant) : pièce d'identité et selfie ;
   validation en quelques heures à quelques jours.
3. **Profil de certificat** : *Certificate profiles* → *Public Trust*, lié
   à l'identité validée. Noter le nom du profil et celui du compte, ainsi
   que l'*endpoint* de la région (ex. `https://weu.codesigning.azure.net/`).
4. **Identité pour la CI** : Microsoft Entra ID → *App registrations* →
   nouvelle application ; créer un *client secret* ; noter *Tenant ID*,
   *Client ID*, secret. Sur la ressource Artifact Signing, *Access control
   (IAM)* → attribuer à cette application le rôle *Artifact Signing
   Certificate Profile Signer*.
5. **Secrets GitHub** du dépôt (Settings → Secrets and variables → Actions) :

   | Secret | Valeur |
   |---|---|
   | `AZURE_TENANT_ID` | Tenant ID de l'application Entra |
   | `AZURE_CLIENT_ID` | Client ID de l'application Entra |
   | `AZURE_CLIENT_SECRET` | secret de l'application |
   | `AZURE_SIGNING_ENDPOINT` | endpoint régional, ex. `https://weu.codesigning.azure.net/` |
   | `AZURE_SIGNING_ACCOUNT` | nom du compte Artifact Signing |
   | `AZURE_SIGNING_PROFILE` | nom du profil de certificat |

6. Pousser un tag : la release suivante est signée. Vérifier sur un poste
   Windows : clic droit sur l'installeur → Propriétés → *Signatures numériques*.

Tant que les secrets sont absents, rien ne change : l'installeur est publié
non signé, comme aujourd'hui.
