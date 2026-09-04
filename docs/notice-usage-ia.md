# Notice d'usage de l'assistant — ce qu'il fait, ce qu'il ne fait pas, comment il se trompe

Écrite pour les orthophonistes qui utilisent Bilan Ortho, au titre de
l'obligation de maîtrise de l'IA (règlement (UE) 2024/1689, article 4,
applicable depuis le 2 février 2025) : dix minutes de lecture qui expliquent
la chaîne, ses limites et ce qui reste à vérifier à chaque bilan. Compléments :
la notice médico-légale (`docs/notice-medico-legale.md`), l'auto-évaluation
AI Act (`docs/conformite/ai-act-auto-evaluation.md`) et la mention
d'information à remettre aux patients (`docs/mention-information-patient.md`).

## 1. La chaîne, étape par étape

1. **Dictée.** Le modèle de reconnaissance vocale (faster-whisper) transcrit
   l'audio sur votre ordinateur (`app/stt.py::transcribe`) ; le fichier audio
   est supprimé dès la transcription terminée. Votre vocabulaire et vos
   corrections (⚙️ Paramètres → Ma dictée) sont appliqués au texte
   (`app/stt.py::_apply_corrections`).
2. **Structuration.** Un modèle de langage local (Ollama) reçoit votre dictée,
   la trame du bilan et ce que les rubriques contiennent déjà ; il propose un
   texte par rubrique et pose des questions quand il lui manque quelque chose
   (`app/prompts.py::build_structure_user`, `app/llm.py::_parse_structure`).
3. **Votre style.** Quelques extraits de vos bilans de référence importés,
   anonymisés à l'import (`app/anonymisation.py::caviarder`), sont montrés au
   modèle pour qu'il adopte votre façon d'écrire (`app/rag.py::retrieve`).
   Les modèles eux-mêmes ne sont jamais modifiés : rien n'est « appris ».
4. **Vérifications automatiques.** Chaque nombre proposé est recherché dans
   votre dictée (`app/verif_chiffres.py::chiffres_non_sources`), chaque nom de
   test surveillé aussi (`app/verif_tests.py::tests_non_sources`), et une
   rubrique trop éloignée de la dictée est signalée
   (`app/verif_texte.py::adossement`). Les signalements restent attachés à
   la rubrique (`app/bilan.py::ajouter_signalements`) jusqu'à votre relecture.
5. **Validation.** Tout ce que l'assistant écrit porte le statut « proposé
   par l'IA » (`app/bilan.py::apply_updates`). Vous relisez, corrigez et
   validez rubrique par rubrique (`app/bilan.py::update_section`), puis le
   bilan entier (`app/bilan.py::set_statut`). Un document non validé s'exporte
   avec la mention « BROUILLON » (`app/export.py::MENTION_BROUILLON`).

## 2. Ce que l'assistant ne fait pas

- Il ne diagnostique pas, ne cote pas, ne décide de rien : les scores et
  les étalonnages sont saisis par vous, la cotation NGAP est calculée d'après
  votre configuration (`app/cotation.py::compute`), jamais proposée par le
  modèle.
- Il n'envoie rien sur internet : les adresses des modèles sont contraintes à
  la boucle locale par la validation de la configuration (`app/models.py`) et
  les modèles Ollama « cloud » sont refusés (`app/llm.py::ModeleCloud`).
- Il n'apprend pas de vos patients : aucun entraînement, aucune mémoire entre
  deux bilans en dehors des extraits de style que vous avez importés.

## 3. Comment il se trompe, et ce que les garde-fous n'attrapent pas

- **Transcription.** Noms de tests, prénoms, chiffres dictés (« quatorze sur
  trente ») peuvent être écorchés. Le vocabulaire personnalisé aide ; relisez
  la dictée avant de la faire structurer.
- **Substitution d'un nom de test.** Un modèle peut remplacer un test par un
  autre, plus connu. Les noms de tests de vos catalogues sont surveillés ; un
  test absent des catalogues ne l'est pas.
- **Fait absent de la dictée.** Un nombre ou un nom de test inventé est
  signalé ; une formulation clinique plausible que vous n'avez pas dictée
  (« l'audition est normale ») ne l'est que si la rubrique entière s'éloigne
  trop de la dictée. C'est le mode d'échec le plus dangereux : lisez chaque
  phrase comme si vous l'aviez écrite vous-même.
- **Sens déformé.** Négation perdue, latéralité inversée, âge mal converti :
  aucun vérificateur ne lit le sens.
- **Oubli.** Ce qui n'a pas été repris de la dictée n'est pas signalé mot à
  mot ; l'application n'avertit que lorsqu'une grande part de la dictée
  n'apparaît nulle part (`app/llm.py::couverture_suspecte`).
- **Dictée trop longue.** Au-delà de la fenêtre du modèle, l'application le
  dit plutôt que de laisser tronquer en silence
  (`app/llm.py::prompt_depasse_contexte`) ; structurez en plusieurs fois.
- **Style.** Les extraits de référence guident la forme, pas le fond. Un
  extrait mal anonymisé pourrait faire remonter un prénom : n'importez que
  des documents dont vous avez vérifié l'anonymisation.

## 4. Ce que vous devez faire, à chaque bilan

1. Relire chaque rubrique proposée, en entier, avant de la valider.
2. Vérifier chaque chiffre et chaque nom de test, signalés ou non.
3. Répondre aux questions de l'assistant ou compléter vous-même : elles
   disent ce qui manque, pas ce qu'il faut conclure.
4. Ne valider et n'exporter qu'un document que vous signeriez tel quel.
5. Ne jamais configurer un modèle « cloud » ni une adresse distante.
6. Informer les patients de l'enregistrement vocal et de l'assistant
   (`docs/mention-information-patient.md`), et cocher la remise dans leur
   dossier.

## 5. En cas de doute ou d'incident

Un comportement anormal du modèle (texte hors sujet, phrases répétées,
langue étrangère) est un motif pour rejeter la proposition entière et
recommencer avec une dictée plus courte. Si vous constatez qu'un chiffre ou
un nom de test inventé n'a pas été signalé, dites-le : c'est un cas à ajouter
aux vérificateurs (`SECURITY.md` pour les failles, une issue GitHub pour le
reste).
