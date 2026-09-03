# Charte d'engagements

**Bilan Ortho** — assistant local de rédaction de bilans orthophoniques
Version 1.9.0 · 18 juillet 2026, révisée le 3 septembre 2026
Titulaire : Alexandre Delahaye · alexandre-delahaye@outlook.fr

Cette charte énonce les engagements que prend Bilan Ortho envers les
orthophonistes qui l'utilisent et envers leurs patients. Chacun s'appuie sur le
fonctionnement réel de l'application, vérifiable dans le code source.

## 1. Vos données ne quittent jamais votre ordinateur

Pas de cloud, pas de compte en ligne, pas de télémétrie. Toutes les données
(patients, bilans, dictées) sont stockées dans une base unique chiffrée
(SQLCipher) sur votre machine, et le serveur de l'application n'écoute que sur
l'adresse locale (127.0.0.1). Ses seuls échanges réseau se font avec le moteur
d'IA Ollama, lui aussi installé sur votre machine. C'est vérifiable : le code
est public et, une fois les modèles installés, l'application fonctionne
entièrement débranchée.

## 2. Aucune IA n'est jamais entraînée sur vos données

C'est structurellement impossible : la dictée est transcrite localement
(faster-whisper) puis l'audio est immédiatement supprimé — ce n'est pas un
réglage, c'est une règle du code —, la rédaction est assistée par un modèle
exécuté localement (Ollama), et l'éditeur du logiciel n'a aucun accès à vos
données : aucun serveur ne les reçoit, aucun mécanisme de collecte n'existe
dans le code. Les modèles ne font que lire (inférence) ; rien de ce que vous
dictez ou écrivez ne sert à entraîner quoi que ce soit.

## 3. L'IA propose, vous signez

Le logiciel ne pose jamais de diagnostic automatique. Tout texte produit par
l'IA est enregistré avec le statut « proposé par l'IA » et le reste tant que le
praticien ou la praticienne ne l'a pas explicitement validé, rubrique par
rubrique. Ce garde-fou est inscrit dans la structure même des données, pas
seulement dans les consignes données au modèle. Seuls l'âge et le sexe sont
transmis à l'IA — jamais l'identité du patient.

## 4. Le logiciel est gratuit et le restera

Bilan Ortho est un logiciel libre publié sous licence AGPL v3. Cette licence
garantit juridiquement que le code restera libre : même si le projet
s'arrêtait demain, n'importe qui pourrait le reprendre, le maintenir et le
redistribuer. La gratuité n'est pas une promesse commerciale, c'est une
propriété de la licence.

## 5. Des limites documentées honnêtement

Bilan Ortho est une aide à la rédaction, pas un dispositif de diagnostic, et
ses limites sont écrites noir sur blanc : une notice médico-légale publique
accompagne le logiciel (`docs/notice-medico-legale.md`), chaque version est
décrite dans un journal des modifications public (`CHANGELOG.md`), les modèles d'IA utilisés
sont identifiés et à poids ouverts (open-weight), et le rythme de maintenance
du projet est annoncé tel qu'il est, sans être surjoué.

## 6. Le chemin gratuit ne disparaîtra jamais

Si un jour du matériel ou des services payants sont proposés autour de
Bilan Ortho, ils resteront strictement optionnels : ils pourront simplifier
l'installation ou l'usage, jamais conditionner l'accès. Le logiciel complet,
installable gratuitement sur votre propre machine, continuera d'exister au
même titre.
