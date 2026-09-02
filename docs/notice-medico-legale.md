# Notice médico-légale — Bilan Ortho

## Nature de l'outil

Bilan Ortho est un **outil d'aide à la rédaction**. Il ne pose aucun diagnostic
et ne prend aucune décision de soin. Il transcrit la dictée de l'orthophoniste,
structure ses propos, met en évidence des éléments et **propose** des
formulations que l'orthophoniste **relit, corrige, complète et valide**.

## Responsabilité

- Le **diagnostic orthophonique relève exclusivement de l'orthophoniste**, qui
  l'établit en autonomie et en reste **seul responsable** (art. L4341-9 CSP).
- Toute production de l'IA est étiquetée « proposition à valider » tant que
  l'orthophoniste ne l'a pas validée. Rien n'est diffusé sans validation humaine.
- Les scores et cotations sont saisis/validés par l'orthophoniste ; l'app ne
  recalcule ni n'invente aucun chiffre.

## Cadre réglementaire (repères, France — juillet 2026)

- Bilan sur **prescription médicale** (sauf cadres dérogatoires : établissements
  de santé mentale, structures médico-sociales, dispositifs de coordination).
- **Compte-rendu obligatoire** adressé au médecin prescripteur, quelles que
  soient ses conclusions, et versé au DMP.
- **Secret professionnel** (art. L4344-2 CSP).
- Cotation **NGAP** — valeurs évolutives par avenants ; paramétrables dans
  l'app ; source de vérité : ameli.fr.

## Confidentialité / RGPD

Voir `RGPD-registre-traitements.md`. L'application fonctionne **100 % en local** :
aucune donnée patient ne quitte la machine (LLM Ollama et transcription Whisper
locaux). N'utilisez **jamais** un modèle Ollama « :cloud » sur des données
patient.
