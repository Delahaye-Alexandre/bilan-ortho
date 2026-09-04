# Déclaration de finalité au regard du règlement (UE) 2017/745 (MDR)

> **Document du responsable du projet, sources vérifiées, non validé par un juriste à ce jour.**

| | |
|---|---|
| **Logiciel** | Bilan Ortho, version 1.12.0 |
| **Éditeur** | Alexandre Delahaye — alexandre-delahaye@outlook.fr |
| **Date** | 18 juillet 2026, révisé le 4 septembre 2026 |

## 1. Finalité déclarée

Bilan Ortho est un logiciel d'**aide à la rédaction et à la mise en forme documentaire** de bilans orthophoniques. Sa finalité est exclusivement documentaire et organisationnelle : transcrire la dictée du professionnel ou de la professionnelle, répartir les propos dictés dans les rubriques du bilan et produire un document exportable.

L'éditeur déclare que le logiciel ne poursuit **aucune finalité médicale au sens de l'article 2, point 1, du règlement (UE) 2017/745** : il n'est destiné ni au diagnostic, ni à la prévention, ni au contrôle, ni à la prédiction, ni au pronostic, ni au traitement ou à l'atténuation d'une maladie.

## 2. Argumentaire de qualification (MDCG 2019-11)

Conformément au guide MDCG 2019-11 relatif à la qualification des logiciels, un logiciel n'est pas un dispositif médical lorsqu'il ne crée ni ne modifie d'information médicale par une analyse qui lui serait propre, destinée à fonder une décision diagnostique ou thérapeutique. C'est le cas de Bilan Ortho, dont les mécanismes effectifs sont les suivants :

- **Le logiciel structure des propos dictés, il ne les interprète pas.** Le contenu clinique provient intégralement du professionnel ou de la professionnelle ; l'assistant de rédaction a pour consignes de ne rien inventer, de ne recalculer ni modifier aucun chiffre, et de ne jamais formuler de diagnostic de sa propre initiative — la rubrique « diagnostic » ne peut que reformuler un diagnostic explicitement énoncé par le praticien ou la praticienne, comme une proposition à confirmer (`app/prompts.py`).
- **Validation humaine systématique et structurelle.** Tout texte issu de l'assistant est enregistré avec le statut `propose_ia` (`app/bilan.py`) ; le passage au statut `valide` est un acte distinct de relecture, correction et validation, rubrique par rubrique (`app/main.py`, `app/bilan.py`). Ce garde-fou est inscrit dans le modèle de données lui-même et ne dépend d'aucun paramétrage. Le bilan complet suit en outre un cycle brouillon → validé → envoyé, sous la seule responsabilité du professionnel ou de la professionnelle, qui le signe.

## 3. Ce que le logiciel ne fait pas

- **Aucune détection ou suspicion de trouble** : le logiciel n'analyse aucune donnée pour suggérer la présence d'une pathologie.
- **Aucun score calculé à visée diagnostique autonome** : la saisie des épreuves applique mécaniquement, aux étalonnages saisis (écart-type, percentile, note standard), des seuils numériques configurés par le praticien ou la praticienne (`interpret_drapeau`, `app/bilan.py` ; réglages « Seuils d'interprétation »). Ce classement, que la personne utilisatrice peut d'ailleurs fixer elle-même, ne constitue pas une conclusion clinique du logiciel.
- **Aucune recommandation thérapeutique** : le logiciel ne propose ni plan de soins, ni orientation, ni traitement.

## 4. Engagement de périmètre

Toute évolution de Bilan Ortho qui ajouterait une finalité médicale au sens de l'article 2, point 1, du MDR (aide au diagnostic, calcul interprétatif autonome, recommandation thérapeutique, etc.) déclencherait, **avant toute diffusion**, une requalification complète du logiciel au regard du règlement (UE) 2017/745 et du guide MDCG 2019-11.

## 5. Signature

Fait à ______________________, le ______________________

Alexandre Delahaye, éditeur du logiciel

Signature : ______________________
