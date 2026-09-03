# Auto-évaluation AI Act — Bilan Ortho

> **Projet de document — à faire relire par un juriste avant publication.**

| | |
|---|---|
| **Date d'établissement** | 18 juillet 2026 |
| **Version du logiciel évaluée** | 1.9.0 (`app/__init__.py`) |
| **Responsable de l'évaluation** | Alexandre Delahaye — alexandre-delahaye@outlook.fr |
| **Référentiel** | Règlement (UE) 2024/1689 (« AI Act »), en tenant compte du paquet « omnibus numérique » adopté en juin 2026 (voir § 6.3) |
| **Statut du logiciel** | Non encore mis sur le marché : dépôt privé à ce jour, publication prévue sous licence AGPL v3 |

---

## 1. Objet et conclusion anticipée

Le présent document constitue l'auto-évaluation de classification du logiciel **Bilan Ortho** au regard du règlement (UE) 2024/1689. Il conclut que le système **n'est pas un système d'IA à haut risque** : à titre principal parce qu'il ne relève d'aucun cas d'usage de l'annexe III, et à titre subsidiaire parce que, même dans une lecture extensive de cette annexe, les conditions de la dérogation de l'**article 6, paragraphe 3** sont remplies. Il est établi **avant toute mise sur le marché** et tient lieu de documentation de l'évaluation au sens de l'article 6, paragraphe 4. Toutes les références au code renvoient au dépôt du projet, version 1.9.0, sous la forme `fichier::symbole` — un test automatisé (`tests/test_docs.py`) vérifie que chaque symbole cité existe.

## 2. Description du système

**Finalité.** Bilan Ortho est un logiciel d'**assistance à la rédaction de bilans orthophoniques**, destiné à des orthophonistes diplômés (usage professionnel). Le praticien ou la praticienne dicte librement ses observations ; le logiciel transcrit la dictée localement (faster-whisper, `app/stt.py`), puis un modèle de langage local répartit les éléments dictés dans les rubriques du bilan et pose des questions de clarification (`app/prompts.py`). Le résultat est exporté en PDF, Word, Markdown ou texte. Le logiciel **ne pose pas de diagnostic, n'interprète pas d'épreuves et n'évalue aucune personne** : il met en forme ce que le professionnel a déjà observé, mesuré et dicté.

**Architecture 100 % locale.** Le serveur n'écoute que sur `127.0.0.1` (`run.sh`, `app/config.py::APP_HOST`, `lanceur.py::main`), avec un filtrage d'hôtes anti-DNS-rebinding (`app/main.py::TrustedHostMiddleware`). Les seuls appels réseau sortants de l'application visent le démon Ollama local ; toute reconfiguration de l'hôte Ollama via l'interface est refusée si l'adresse n'est pas locale (`app/config.py::hote_est_local`, `app/models.py::_exiger_hote_local`). Il n'existe **aucune télémétrie, aucun compte en ligne, aucun service tiers**. Les données (patients, bilans) résident dans une base SQLCipher chiffrée sur le poste de l'utilisateur ou de l'utilisatrice ; l'audio de dictée est **toujours supprimé après transcription**, sans exception ni réglage (`app/stt.py::transcribe` ; aucune clé de configuration ne s'y rapporte, `app/config.py::DEFAULTS`) ; seuls l'âge et le sexe du patient sont transmis au modèle de langage, **jamais l'identité** (`app/main.py::_structurer`, `app/patient.py::age_texte`). Réserve de transparence : la contrainte d'hôte local s'applique par défaut et via l'interface ; une variable d'environnement `OLLAMA_HOST` définie par la personne utilisatrice peut désigner un autre démon Ollama.

**Modèles d'IA intégrés.** Le projet **ne développe, n'entraîne ni n'affine aucun modèle**. Il exécute localement, via Ollama et faster-whisper, des modèles open-weight tiers : un LLM (par défaut `qwen2.5:7b-instruct-q4_K_M`, clé `llm.model` de `app/config.py::DEFAULTS`), un modèle d'embeddings (`nomic-embed-text`, clé `embeddings.model` de `app/config.py::DEFAULTS`) et Whisper pour la dictée (`app/stt.py::resolved`). Ces modèles sont diffusés par leurs éditeurs sous licences ouvertes (à confirmer modèle par modèle avant publication). Le logiciel ne distribue pas les poids : ils sont téléchargés par le démon Ollama local de la personne utilisatrice (`app/main.py::pull_modele`).

**Validation humaine systématique (garde-fou structurel).** Chaque rubrique du bilan porte un statut `vide | propose_ia | valide` (table `section`, `app/db.py::_SCHEMA`). **Tout texte produit par l'IA est enregistré au statut `propose_ia`** (`app/bilan.py::apply_updates`) ; son passage au statut `valide` est un **acte distinct et volontaire** du praticien ou de la praticienne, rubrique par rubrique (route `PUT /api/bilans/{id}/sections/{cle}`, `app/models.py::SectionPut`, `app/bilan.py::update_section`). Le bilan suit lui-même un cycle `brouillon → valide → envoye` tracé (table `bilan`, `app/db.py::_SCHEMA` ; `app/bilan.py::set_statut`). Ce mécanisme est **structurel et non contournable par configuration**. Un second garde-fou, au niveau du prompt, interdit au modèle de poser un diagnostic de sa propre initiative et de rien inventer (règles « N'INVENTE RIEN » et « Tu ne poses JAMAIS de diagnostic de ta propre initiative », `app/prompts.py::STRUCTURE_SYSTEM`) ; un diagnostic énoncé par le professionnel n'est reformulé que « comme une proposition à confirmer » (même consigne). Par transparence : ce prompt est personnalisable par configuration (clé `prompts.structure_system` de `app/config.py::DEFAULTS`) ; le garde-fou par statuts, lui, ne l'est pas.

## 3. Qualification et rôles au sens du règlement

- Bilan Ortho est un **système d'IA** qui **intègre des modèles d'IA à usage général** (GPAI, article 3, point 63) fournis par des tiers. Le titulaire du projet est donc, à l'égard de ces modèles, un **« fournisseur en aval »** au sens de l'article 3, point 68 (fournisseur d'un système d'IA intégrant un modèle d'IA fourni par une autre entité).
- Lors de la mise à disposition publique du logiciel, le titulaire deviendra **fournisseur du système d'IA** au sens de l'article 3, point 3. Les obligations du chapitre V relatives aux modèles à usage général (notamment l'article 53) pèsent sur les **fournisseurs des modèles** (éditeurs de Qwen, Whisper, nomic-embed-text), non sur le fournisseur en aval ; le projet ne met par ailleurs aucun modèle sur le marché, puisqu'il ne redistribue pas les poids.
- Les orthophonistes utilisant le logiciel dans leur cadre professionnel seront des **déployeurs** au sens de l'article 3, point 4.
- Conformément à l'article 25, quiconque modifierait la destination du système de sorte qu'il devienne à haut risque assumerait les obligations de fournisseur correspondantes (voir l'engagement du § 7).

La qualification éventuelle au titre du règlement (UE) 2017/745 sur les dispositifs médicaux relève d'une analyse distincte, hors du périmètre du présent document ; en l'état, le logiciel ne revendique aucune finalité de diagnostic, de prévention ou de traitement. **Point à faire confirmer lors de la relecture juridique.**

## 4. Analyse au regard de l'annexe III

L'article 6, paragraphe 2, qualifie de haut risque les systèmes relevant des cas d'usage de l'annexe III. Examen des catégories susceptibles d'être invoquées :

| Point de l'annexe III | Analyse |
|---|---|
| **1. Biométrie** (identification, catégorisation, reconnaissance des émotions) | La dictée traite la voix du praticien ou de la praticienne, mais uniquement pour la **transcrire** ; aucune identification, catégorisation biométrique ni reconnaissance des émotions n'est effectuée. Hors champ. |
| **3. Éducation et formation professionnelle** | Les bilans concernent souvent des troubles des apprentissages, mais le système ne détermine l'accès à aucun établissement, n'évalue aucun acquis d'apprentissage aux fins d'une décision éducative et ne surveille aucun examen. Hors champ. |
| **5 a) Éligibilité aux prestations et services essentiels, y compris les soins de santé** | Vise l'évaluation de l'**éligibilité** par ou pour des autorités publiques. Bilan Ortho n'évalue aucune éligibilité et n'est pas destiné à des autorités. Hors champ. |
| **5 c) Évaluation des risques et tarification en assurance vie et santé** | Sans objet. |
| **5 d) Appels d'urgence, dispatching des secours, triage des patients en médecine d'urgence** | Sans objet : aucun contexte d'urgence, aucun triage. |
| **2, 4, 6, 7, 8** (infrastructures critiques ; emploi ; répression ; migration ; justice et processus démocratiques) | Manifestement étrangers à la finalité du système. |

**Conclusion principale :** le système ne relève d'aucun cas d'usage de l'annexe III et n'est donc pas à haut risque au titre de l'article 6, paragraphe 2.

## 5. À titre subsidiaire : dérogation de l'article 6, paragraphe 3

Même si une lecture extensive rattachait l'usage du logiciel au domaine de la santé de l'annexe III, le système ne présenterait pas de risque important de préjudice pour la santé, la sécurité ou les droits fondamentaux, **notamment en ce qu'il n'influence pas matériellement le résultat de la prise de décision**. Une seule des conditions de l'article 6, paragraphe 3, suffit ; trois sont ici remplies :

**a) Tâche procédurale étroite.** Le système accomplit deux opérations bornées : transcrire une dictée et répartir les éléments dictés dans des rubriques prédéfinies. Le prompt lui interdit d'inventer (« N'INVENTE RIEN : utilise uniquement ce qui a été dicté ou répondu »), de recalculer ou modifier un chiffre (règle « CHIFFRES ») et de poser un diagnostic de sa propre initiative — les trois dans `app/prompts.py::STRUCTURE_SYSTEM`. Il s'agit d'une mise en forme, non d'une évaluation.

**b) Amélioration du résultat d'une activité humaine préalablement accomplie.** Le système intervient **après** l'activité clinique : l'anamnèse, la passation des épreuves et les observations sont l'œuvre du professionnel ; le logiciel améliore la restitution écrite de ce travail déjà accompli. Un diagnostic n'apparaît dans le texte proposé que si le praticien ou la praticienne l'a explicitement énoncé, et il est alors reformulé comme une proposition à confirmer (`app/prompts.py::STRUCTURE_SYSTEM`).

**d) Tâche préparatoire à une évaluation.** Toute production de l'IA est enregistrée au statut `propose_ia` (`app/bilan.py::apply_updates`) et ne constitue qu'une **préparation** à l'évaluation humaine : rien ne devient définitif sans validation expresse, rubrique par rubrique (`app/bilan.py::update_section`), puis validation et envoi du bilan entier, actes humains tracés (`app/bilan.py::set_statut`).

**Le système ne remplace pas l'appréciation humaine.** Le règlement et les lignes directrices de la Commission sur la classification des systèmes à haut risque précisent qu'ajouter une intervention humaine ne suffit pas, à soi seul, à écarter la qualification. Ici, l'intervention humaine n'est pas un correctif ajouté : **la finalité même du système est la rédaction assistée d'un document dont l'auteur reste le professionnel**. Le garde-fou de validation est structurel (statuts en base, non modifiables par configuration), et l'application se verrouille automatiquement en cas d'inactivité, y compris sans aucune requête (`app/security.py::enforce_inactivity`).

**Absence de profilage.** La dérogation est exclue en cas de profilage de personnes physiques (article 6, paragraphe 3, dernier alinéa ; définition de l'article 3, point 52, renvoyant au RGPD). Le système n'évalue ni ne prédit automatiquement des aspects personnels : il restitue et structure ce qui a été dicté par le professionnel, sans inférence propre sur la personne. **Point d'attention signalé pour la relecture juridique**, s'agissant de données de santé.

## 6. Obligations résiduelles

### 6.1 Documentation et enregistrement (article 6, paragraphe 4 ; article 49, paragraphe 2)

Le présent document constitue la documentation de l'évaluation exigée par l'article 6, paragraphe 4, établie **avant la mise sur le marché** ; elle sera tenue à la disposition des autorités compétentes sur demande. Si la qualification retenue in fine était celle d'un système relevant de l'annexe III mais non à haut risque en vertu de l'article 6, paragraphe 3, l'**enregistrement dans la base de données de l'UE** prévu à l'article 49, paragraphe 2, serait requis avant la mise sur le marché. La conclusion principale (système hors annexe III) n'emporte pas cette obligation. **Point à trancher lors de la relecture juridique.**

### 6.2 Transparence (article 50, applicable à compter du 2 août 2026)

- **Article 50, paragraphe 1** (information des personnes interagissant avec une IA) : l'usage de l'IA est évident et explicitement signalé à la personne utilisatrice — les contenus générés apparaissent avec le statut « proposé par l'IA » et appellent une validation expresse.
- **Article 50, paragraphe 2** (marquage lisible par machine des contenus synthétiques, y compris le texte) : une exception est prévue lorsque le système exerce une **fonction d'assistance pour l'édition standard** ou **ne modifie pas substantiellement les données d'entrée fournies ni leur sémantique**. Bilan Ortho structure sans inventer, à partir des seules données dictées ; cette exception paraît applicable. **Position à confirmer par le juriste** ; à défaut, un marquage lisible par machine sera ajouté aux contenus générés avant la mise sur le marché.
- **Article 50, paragraphe 4** (texte publié pour informer le public) : sans objet — les bilans sont des documents cliniques individuels, non publiés à destination du public, et font en tout état de cause l'objet d'un examen humain systématique.

### 6.3 Calendrier d'application (vérifié au 18 juillet 2026)

| Échéance | Objet |
|---|---|
| 1er août 2024 | Entrée en vigueur du règlement |
| 2 février 2025 | Interdiction des pratiques d'IA inacceptables |
| 2 août 2025 | Obligations relatives aux modèles à usage général (chapitre V), gouvernance, sanctions |
| 2 août 2026 | Application générale, dont l'article 50 (période de grâce jusqu'au 2 décembre 2026 pour le marquage par les systèmes existants) |
| **2 décembre 2027** | Systèmes à haut risque de l'**annexe III** — échéance initialement fixée au 2 août 2026, **reportée** par le paquet « omnibus numérique » (accord politique de mai 2026, approuvé par le Parlement européen le 16 juin 2026 et par le Conseil le 29 juin 2026 ; publication au Journal officiel attendue à la date du présent document) |
| 2 août 2028 | Systèmes à haut risque de l'article 6, paragraphe 1 (annexe I, produits réglementés) — au lieu du 2 août 2027 |

La présente auto-évaluation sera relue après publication du paquet « omnibus numérique » au Journal officiel, ainsi qu'au regard des lignes directrices de la Commission relatives à la classification des systèmes à haut risque.

## 7. Engagement de réévaluation

Le titulaire du projet s'engage à **ne jamais ajouter** de fonction de suspicion, de détection ou de dépistage d'un trouble, de score ou d'interprétation automatique d'épreuves, ni de proposition diagnostique à l'initiative du système, **sans réévaluation complète et préalable** de la présente auto-évaluation (annexe III, article 6, qualification au titre du règlement sur les dispositifs médicaux). Toute personne qui modifierait la destination du système dans un tel sens assumerait les responsabilités correspondantes (article 25). La personnalisation du prompt offerte par le logiciel ne saurait être utilisée pour contourner l'interdiction de diagnostic ; le garde-fou structurel de validation humaine par statuts sera maintenu dans toutes les versions futures.

## 8. Conclusion motivée

Bilan Ortho, version 1.9.0, est un outil local d'assistance à la rédaction, dont chaque production est une simple proposition soumise à la validation expresse d'un professionnel qui demeure seul auteur de l'évaluation clinique. Il ne relève d'aucun cas d'usage de l'annexe III du règlement (UE) 2024/1689 et, à titre subsidiaire, remplit les conditions a), b) et d) de la dérogation de l'article 6, paragraphe 3, sans effectuer de profilage. **Il n'est donc pas un système d'IA à haut risque.** Les obligations résiduelles identifiées (documentation au titre de l'article 6, paragraphe 4 ; transparence au titre de l'article 50 ; enregistrement éventuel au titre de l'article 49, paragraphe 2) sont traitées au § 6. Cette conclusion sera réexaminée à chaque évolution fonctionnelle significative du logiciel et à chaque évolution du cadre réglementaire.

---

Fait à : ______________________ , le : ______________________

**Alexandre Delahaye**, responsable du projet

Signature : ______________________

*Document établi le 18 juillet 2026 pour la version 1.5.0 ; révisé le 3 septembre 2026 pour la version 1.9.0 (références au code par symbole, vérifiées par test). Projet de document — à faire relire par un juriste avant publication.*
