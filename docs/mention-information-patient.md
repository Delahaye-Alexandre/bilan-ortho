# Mention d'information — modèle à remettre au patient

> Modèle à compléter et à remettre (ou à afficher en salle d'attente) par
> l'orthophoniste, responsable de traitement. Il répond à l'obligation
> d'information des articles 12 et 13 du RGPD pour les données traitées avec
> Bilan Ortho. Il ne vaut pas conseil juridique : adaptez-le à votre exercice
> (société, plusieurs professionnels, autres logiciels). Dans l'application,
> la case « Mention d'information remise » du dossier patient garde la date
> de la remise (`app/patient.py::set_information`) : c'est votre trace, pas
> un consentement — la prise en charge n'en exige pas. Le modèle suit les
> éléments que la CNIL attend d'une mention d'information (identité du
> responsable, finalités et base légale, destinataires, transferts, durée,
> droits et réclamation, caractère nécessaire des données, décision
> automatisée) et sa recommandation d'une mention courte doublée d'une
> mention complète — vérifié le 4 septembre 2026 sur cnil.fr (« RGPD :
> exemples de mentions d'information »).

---

## Information sur le traitement de vos données — bilan orthophonique

**Responsable du traitement** : [prénom, nom], orthophoniste —
[adresse du cabinet] — [téléphone, courriel].

**Pourquoi vos données sont traitées.** Pour réaliser votre bilan
orthophonique et rédiger le compte-rendu adressé au médecin qui l'a prescrit,
comme la réglementation l'exige. Base juridique : la prise en charge de votre
santé (RGPD, article 6, paragraphe 1, b et c ; article 9, paragraphe 2, h).
Le secret professionnel s'applique.

**Quelles données.** Votre identité (nom, prénom, date de naissance), les
éléments d'histoire et d'observation recueillis, les résultats des épreuves,
le compte-rendu. Pendant ou après la séance, l'orthophoniste peut **dicter à
voix haute** ses observations à un logiciel d'aide à la rédaction
(Bilan Ortho) : l'enregistrement est transcrit sur l'ordinateur du cabinet
puis **supprimé aussitôt** ; seul le texte est conservé. Vous pouvez demander
que la dictée ne soit pas utilisée pour votre dossier : l'orthophoniste
rédige alors sans elle.

**Un assistant d'intelligence artificielle, sur l'ordinateur du cabinet.**
Le logiciel aide l'orthophoniste à structurer et à mettre en forme ce qui a
été dicté. Il fonctionne **entièrement en local** : aucune donnée n'est
envoyée sur internet ni à un prestataire. Il ne pose aucun diagnostic et ne
prend aucune décision : chaque phrase qu'il propose est relue, corrigée et
validée par l'orthophoniste, qui reste l'unique auteur du compte-rendu
(aucune décision automatisée au sens de l'article 22 du RGPD).

**Qui reçoit vos données.** L'orthophoniste ; le médecin prescripteur
(compte-rendu de bilan) ; votre Dossier Médical Partagé le cas échéant ;
avec votre accord, d'autres professionnels qui vous suivent ou l'école.
Aucun sous-traitant, aucun transfert hors de l'Union européenne.

**Ces informations sont-elles obligatoires ?** L'identité, la date de
naissance et les éléments cliniques sont nécessaires à la réalisation du
bilan et à son compte-rendu ; sans eux, le bilan ne peut pas être réalisé ni
son compte-rendu adressé au médecin. La dictée vocale, elle, n'est qu'un
moyen de rédaction : vous pouvez la refuser sans conséquence sur votre prise
en charge.

**Combien de temps.** [Durée retenue par le cabinet pour les dossiers de
soins — à préciser ; les sauvegardes chiffrées de l'ordinateur peuvent
conserver un dossier quelques semaines après sa suppression.]

**Vos droits.** Accès, rectification, effacement (dans les limites des
obligations de conservation), limitation, opposition pour un motif tenant à
votre situation, portabilité. Adressez-vous à l'orthophoniste aux
coordonnées ci-dessus. Vous pouvez aussi saisir la CNIL (cnil.fr) si vous
estimez que vos droits ne sont pas respectés.

**Patient mineur ou protégé.** L'information est donnée aux personnes
titulaires de l'autorité parentale ou chargées de la protection, et au
patient lui-même sous une forme adaptée à son âge et à sa compréhension.

**Sécurité.** Les données sont chiffrées sur l'ordinateur du cabinet, dont
l'accès est protégé par une phrase secrète connue de l'orthophoniste
seulement ; l'application se verrouille d'elle-même après un temps
d'inactivité.

Information remise le : ______________________

---

## Version courte (affichette salle d'attente)

> **Vos données, votre bilan.** Pour rédiger votre compte-rendu de bilan,
> l'orthophoniste utilise un logiciel d'aide à la rédaction qui fonctionne
> entièrement sur l'ordinateur du cabinet, sans envoi sur internet. Les
> observations peuvent être dictées à voix haute : l'enregistrement est
> transcrit puis supprimé aussitôt. L'orthophoniste relit et valide chaque
> phrase ; le logiciel ne pose aucun diagnostic. Vous disposez d'un droit
> d'accès, de rectification et d'effacement : demandez la fiche complète.
