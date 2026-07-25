# Bilans de référence — amorces de style

Ces fichiers sont des **bilans entièrement fictifs** (patients, scores et
contextes inventés), rédigés pour servir d'**amorces de style** : ils donnent à
l'assistant des exemples de rédaction clinique dès le premier jour, dans les
11 domaines de l'application.

**Import en un clic** : dans la barre latérale, « Mes bilans de référence » →
« Charger les bilans d'exemple ». Chaque fichier est indexé avec son domaine ;
re-cliquer remplace le pack (jamais de doublon). Les entrées portent la mention
« exemple » et se retirent d'un clic (« Retirer les exemples »).

**La vraie valeur vient de vos propres bilans** : importez vos PDF, .docx,
.odt (LibreOffice) ou fichiers texte (les PDF scannés nécessitent Tesseract)
et l'IA s'inspirera de *votre* style — tournures, niveau de détail, plan.
Retirez ensuite ces amorces fictives : votre style prendra toute la place.

Aucune trame d'auteur tierce n'est redistribuée ici : la structure suit le
tronc commun réglementaire (arrêté du 25/07/2023), rédaction originale.

| Fichier | Domaine (clé) |
|---|---|
| `bilan-fictif-langage-oral.txt` | Langage oral (`langage_oral`) |
| `bilan-fictif-langage-ecrit.txt` | Langage écrit (`langage_ecrit`) |
| `bilan-fictif-parole-articulation.txt` | Parole / articulation / phonologie (`parole_articulation`) |
| `bilan-fictif-cognition-mathematique.txt` | Cognition mathématique (`cognition_mathematique`) |
| `bilan-fictif-communication-tsa.txt` | Communication & handicap / TSA (`communication_tsa`) |
| `bilan-fictif-voix.txt` | Voix (`voix`) |
| `bilan-fictif-deglutition-omf.txt` | Déglutition / fonctions oro-myo-faciales (`deglutition_omf`) |
| `bilan-fictif-neuro-acquise.txt` | Neurologie acquise (`neuro_acquise`) |
| `bilan-fictif-surdite.txt` | Surdité (`surdite`) |
| `bilan-fictif-begaiement.txt` | Bégaiement / fluence (`begaiement`) |
| `bilan-fictif-oralite-nourrisson.txt` | Oralité alimentaire du nourrisson (`oralite_nourrisson`) |

La clé de domaine se déduit du nom : `bilan-fictif-<domaine>.txt`, tirets →
underscores. Tout fichier ajouté ici doit suivre cette convention et les
en-têtes du tronc commun (un test l'y contraint : `tests/test_base.py`).

## Sources externes — consultables, mais non redistribuables

Il n'existe aujourd'hui **aucun corpus de bilans rédigés librement
redistribuable** (vérification faite le 2026-07-26 : droits d'auteur, licences,
CGU). Les ressources ci-dessous ne peuvent donc pas être embarquées dans ce
dépôt — mais **vous** pouvez les télécharger pour votre propre usage et les
importer dans votre base locale (usage privé) :

- **Orthonie** — 8 modèles de CRBO fictifs conformes à l'avenant 20, gratuits
  au téléchargement : <https://orthonie.fr/modeles-crbo-gratuits>
  (© MINDFUEL, tous droits réservés — pas de redistribution).
- **DUMAS** — mémoires d'orthophonie avec bilans en annexe :
  <https://dumas.ccsd.cnrs.fr> (licences CC restrictives ; attention, la
  plupart décrivent des patients réels anonymisés — à ne pas importer si vous
  partagez votre machine).

N'importez jamais dans l'application un bilan d'un patient réel qui ne serait
pas le vôtre.
