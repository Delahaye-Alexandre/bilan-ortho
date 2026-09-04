# Plan « mise en forme » — validé le 2026-09-03

## Constat de départ

- Le **style rédactionnel** du praticien est déjà repris : les bilans de
  référence importés sont découpés par rubrique, anonymisés, puis réinjectés
  dans le prompt de structuration (`rag.py`, `prompts.py`).
- La **mise en forme** est perdue à l'import (`importer.py` ne garde que le
  texte) et figée à l'export (`export.py` : tailles et marges en dur dans
  `to_pdf`, modèle vide de python-docx pour le Word).
- Les rubriques sont du **texte brut** : ni gras, ni listes. Le praticien
  finissait la mise en forme dans Word après export.
- La **structure** (ordre et intitulés des rubriques) est déjà configurable
  (Paramètres → Trame des bilans).

## Lots, dans l'ordre

| Lot | Contenu | Estimation |
|---|---|---|
| A | Texte riche dans les rubriques : gras, italique, souligné, listes | 3 à 5 jours |
| B | Mise en forme du document : police, titres, marges, logo, aperçu | 2 à 3 jours |
| C | Reprendre la trame d'un bilan importé | 1 à 2 jours |
| D | Gabarit .docx personnel : styles, en-tête, pied de page, logo | 3 à 5 jours |

Le lot A vient en premier parce qu'il restructure la représentation
intermédiaire de l'export (`export._content`) que le lot B paramètre ensuite.
Le .odt (export et gabarit) est différé : le .docx est lu par LibreOffice,
Google Docs, Pages et OnlyOffice ; l'inverse n'est pas vrai.

## Lot A — texte riche

### Décisions validées

1. Gras, italique, **souligné** et listes (à puces, numérotées). Rien d'autre :
   pas de titres, de tableaux, de liens ni d'images dans une rubrique.
2. L'IA **peut mettre en forme**, sobrement, **par défaut** ; réglage
   désactivable par le praticien (`style.mise_en_forme_ia`). Elle calque sa
   mise en forme sur celle des bilans de référence importés, dont le gras, l'italique,
   le souligné et les listes sont désormais conservés à l'import (.docx).
3. Le **collage depuis Word / LibreOffice / Google Docs conserve** gras,
   italique, souligné et listes ; tout le reste est retiré.

### Format stocké

`section.contenu` reste une colonne texte, sans migration : Markdown
restreint. `**gras**`, `*italique*`, `<u>souligné</u>`, listes `- item` et
`1. item` (continuation d'un élément par deux espaces), paragraphes séparés
par une ligne vide, retour à la ligne simple conservé dans un paragraphe. Un
contenu existant (texte brut) est déjà valide. Un marqueur non fermé est du
texte, jamais une erreur. Le module `app/texte_riche.py` est la seule
implémentation serveur (analyse, sérialisation canonique, version en clair).

### Changements

- **`app/texte_riche.py`** (nouveau) : `analyser`, `serialiser`, `en_clair`.
- **`app/export.py`** : nouveau bloc `riche` pour le contenu des rubriques ;
  Markdown canonique, texte en clair, Word avec runs et styles de liste (avec
  reprise de la numérotation à 1 pour chaque liste), PDF avec balisage de
  paragraphe et listes reportlab.
- **`app/importer.py`** : l'extraction .docx conserve gras, italique,
  souligné et listes ; les titres restent en clair pour le découpage.
- **`app/prompts.py`, `app/config.py`, `app/main.py`, `app/bilan.py`** :
  consigne de mise en forme (activable), texte remis en clair si le réglage est
  désactivé, vérificateurs (chiffres, tests, adossement) nourris avec la
  version en clair sans numérotation.
- **`app/static/index.html`** : zone éditable par rubrique avec barre (gras,
  italique, souligné, listes) et raccourcis Ctrl+B/I/U ; Entrée = paragraphe,
  Maj+Entrée = retour à la ligne ; conversions pures Markdown ↔ DOM ; collage
  HTML nettoyé (Word, LibreOffice, Google Docs) ; copie en texte + HTML ;
  case « L'IA peut mettre en forme » dans Paramètres → Style. Le contenu est
  toujours construit nœud par nœud, jamais injecté en HTML brut.

### Définition de « fini »

`pytest` + `ruff check .` + suites UI vertes (dont la nouvelle
`tests/ui/test_texte_riche_ui.mjs`), CHANGELOG et guide de test à jour.

## Lot B — mise en page du document (fait le 2026-09-04)

### Décisions

1. Une section de configuration `mise_en_page` (défauts dans `config.py`,
   patch validé par `models.MiseEnPagePatch`), lue par `to_docx` et `to_pdf`
   via `export.mise_en_page(cfg)` : police, taille du corps, interligne,
   marges, couleur des titres, rubriques numérotées, numéros de page, logo
   (position, hauteur). Markdown et texte ne connaissent que la numérotation.
2. Polices proposées : celles de Word (Calibri, Arial, Verdana, Times New
   Roman, Georgia). Le PDF incorpore le fichier TrueType s'il est trouvé sur
   la machine (`export._polices_pdf`, dossiers Windows, Linux, macOS), sinon
   Helvetica ou Times selon les empattements — jamais d'échec.
3. Le logo est une image vérifiée par Pillow (PNG ou JPEG, pas l'extension),
   réduite à 400 px de haut, ré-encodée et rangée en base64 dans la
   configuration chiffrée. Déposé et retiré par `PUT`/`DELETE
   /api/config/logo` dès le choix du fichier, jamais par le `PUT /api/config`
   (refusé : 422). Un logo illisible ne bloque pas l'export.
4. Numérotation des rubriques : tous les titres de niveau 2 à la suite
   (résultats et cotation compris), sans toucher au contenu stocké.
5. Numéros de page : « Page i / n » en pied de page, champs `PAGE` /
   `NUMPAGES` dans le Word, canvas à deux passes dans le PDF.
6. Aperçu : `POST /api/config/mise_en_page/apercu` reçoit les réglages de
   l'écran (non enregistrés), les pose sur la configuration en place (logo
   compris) et renvoie le PDF d'un bilan fictif (`export.bilan_exemple`),
   affiché dans un cadre de la section, regroupé à 400 ms.
7. Retour aux valeurs recommandées de la section clé par clé, le logo reste.
8. Le Word passe de « Title / Heading 1 » à « Heading 1 / Heading 2 » (styles
   posés explicitement : police, taille, couleur, renvois au thème retirés).
   Le lot D (gabarit .docx) court-circuitera `export._docx_mise_en_page`.

### Vérification

`tests/test_mise_en_page.py` (Word, PDF, logo, numérotation, polices de
repli et TrueType, bilan d'exemple, routes) ; `tests/ui/test_parametres_ui.mjs`
(section, listes, pastilles, logo, aperçu, enregistrement, retour aux valeurs
recommandées) ; pytest, ruff et les six suites UI verts.

## Lot C — reprendre la trame d'un bilan importé (fait le 2026-09-04)

### Décisions

1. L'extraction rend des lignes structurées (`importer.Ligne` : niveau de
   titre stylé Word/LibreOffice, paragraphe entièrement en gras) ; le texte
   brut (`extract_text`) ne change pas.
2. `importer.proposer_trame_lignes` : toujours les mots-clés du tronc commun,
   plus le signal le plus sûr que le document offre — titres stylés (au
   niveau de plan qui en compte au moins deux), sinon gras, sinon lignes
   courtes isolées (sept mots au plus, majuscule initiale, sans chiffre ni
   ponctuation finale, suivies d'un vrai paragraphe). Titre du document et
   doublons écartés ; numérotation en tête retirée ; clé = mot-clé si
   reconnu et libre, sinon `cle_de_rubrique(titre)` (unique). Moins de deux
   rubriques ou plus de vingt-cinq : pas de proposition.
3. Deux entrées : `POST /api/config/trame/analyse` (fichier, jamais conservé,
   nom non journalisé) depuis l'éditeur de trame ; et `trame_proposee` dans la
   réponse de `POST /api/references`, exploité par un lien « Reprendre sa
   trame » qui ouvre l'éditeur. La proposition remplace la liste EN ÉDITION ;
   seul « Enregistrer la trame » écrit.
4. À l'import, un titre stylé sans mot-clé ouvre son propre extrait avec la
   clé de la rubrique en cours (héritée) ; `rag.retrieve` accepte aussi un
   extrait dont l'intitulé (`cle_de_rubrique`) est la clé demandée. Le gras
   ne découpe pas à l'import (extraits moins morcelés).

### Vérification

`tests/test_trame_import.py` ; sections 22 bis et 26 bis de
`tests/ui/test_robustesse_ui.mjs`, scénario 6 de `tests/ui/test_relecture_ui.mjs`.

## Lot D — gabarit Word personnel (fait le 2026-09-04)

### Décisions

1. Le gabarit est un document Word du praticien (.docx ; un modèle .dotx est
   converti en réécrivant son type de contenu, un .docm/.dotm ou un projet
   VBA embarqué est refusé). `export.preparer_gabarit` vérifie l'enveloppe
   (zip Word, contenu décompressé borné), le décrit (nom nettoyé, taille,
   date, styles utiles présents parmi `STYLES_GABARIT`, en-tête et pied de
   page garnis) et met en page le bilan d'exemple avant d'accepter : un
   gabarit accepté ne fait pas échouer un export.
2. Les octets vivent dans la table `config` sous leur propre clé
   (`ConfigStore.CLE_GABARIT`, base64), pas dans les surcharges : la
   configuration est relue à chaque requête, le gabarit au seul export Word.
   La description seule est dans `mise_en_page.gabarit` ; `ConfigStore._ecrire`
   retire les octets dès que la description disparaît (retrait, section
   effacée, réinitialisation). `MiseEnPagePatch` refuse la clé `gabarit`
   comme `logo` ; nouvelle clé `gabarit_porte_identite`.
3. `to_docx(b, cfg, gabarit)` : le document part du gabarit vidé de son corps
   (tout sauf le `sectPr` final : un gabarit à plusieurs sections garde la
   dernière) ; `_docx_mise_en_page` n'est pas appelée, les styles et sections
   sont ceux du gabarit. Complément de ce qu'il ne définit pas : Heading 1/2
   créés (style intégré, basé sur Normal, taille du corps du gabarit ou des
   défauts du document + 6/+2, couleur des titres de la configuration) ;
   listes écrites en texte (« • », « 1. », retrait suspendu, espacement
   serré : un document Word neuf n'a pas de style de liste, c'est le cas
   courant) sans paragraphe orphelin — le
   repli du lot B en laissait un, `add_paragraph(style=…)` créant le
   paragraphe avant d'échouer ; tableau quadrillé par `tblBorders` sans
   « Table Grid » ; numéros de page ajoutés seulement à un pied de page vide
   quand le réglage est coché.
4. `_content(b, cfg, gabarit=True)` : pas de logo (le papier à en-tête est le
   gabarit), pas d'identité du cabinet en tête si `gabarit_porte_identite`.
   Le PDF ignore le gabarit : l'écran le dit, et « Exemple Word »
   (`POST /api/config/mise_en_page/apercu?format=docx`, réglages de l'écran,
   gabarit en place) permet de juger dans Word.
5. Routes `PUT` (fichier, 5 Mo, 413/422), `GET` (le .docx conservé, sous son
   nom) et `DELETE /api/config/gabarit` ; l'export Word d'un bilan lit le
   gabarit dans la même transaction et, s'il échoue dessus, répond 500 avec
   un message qui renvoie au retrait ou au PDF plutôt qu'un document sans
   papier à en-tête.
6. Écran : bloc « Mon papier à en-tête (gabarit Word) » sous le logo —
   description en clair de ce qui est repris et complété, lien « Récupérer le
   fichier », « Retirer le gabarit », « Exemple Word », case « porte déjà
   l'identité ». Le retour aux valeurs recommandées de la section garde le
   gabarit comme le logo.

### Vérification

`tests/test_gabarit_docx.py` (description, conversion .dotx, refus, export
sur gabarit, replis, pied de page, identité, sections multiples, routes,
réinitialisation) ; section 7 bis de `tests/ui/test_parametres_ui.mjs` ;
pytest, ruff et les six suites UI verts ; document ouvert dans Word (Windows)
par automatisation sur un papier à en-tête créé par Word lui-même.
