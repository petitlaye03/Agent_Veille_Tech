---
title: "Brief produit — Agent de veille IA"
status: ready
created: 2026-07-20
updated: 2026-07-24
---

# Brief produit : agent de veille IA

## Résumé

Un agent qui produit chaque nuit une page de veille, consultable au réveil sur téléphone, couvrant l'IA, la data et l'informatique en général. Il remplit trois rôles : **aiguiller** vers ce qui mérite d'être lu ou écouté, **élargir** le champ bien au-delà des sources déjà suivies, et **découvrir** de nouvelles sources au fil du temps.

L'utilisateur est Abdoulaye Ndour, Junior Data Scientist à Dakar, en fin de premier stage (novembre 2026), qui vise des postes en IA. Sa veille actuelle repose sur cinq ou six podcasts francophones grand public, écoutés en marchant. C'est une habitude qui tient depuis des mois — mais elle est étroite : peu de technique, pas de recherche, pas d'ingénierie, et une fraction infime de ce qui se publie.

Le pari du produit tient en une phrase : **la valeur de l'agent est exactement ce qu'il apporte que l'utilisateur n'a pas déjà.** Un agrégateur qui relaie ses podcasts actuels n'aurait aucune raison d'exister. Français et anglais sont traités à égalité, sans hiérarchie.

## Le problème

Abdoulaye vise des postes en IA sans savoir ce que le marché exige techniquement. Ses podcasts le tiennent au courant de l'air du temps ; ils ne lui disent pas quels outils, quelles architectures, quelles compétences reviennent dans les conversations professionnelles.

Sa veille souffre de deux angles morts. **Elle est étroite en surface** : cinq ou six podcasts francophones grand public, là où l'écosystème compte des centaines de sources actives — recherche, blogs d'ingénierie, communautés, publications de laboratoires. **Et elle est étroite en profondeur** : du commentaire d'actualité, presque jamais de technique. Rien qui lui dise ce qu'il faut apprendre.

Il a déjà tenté d'y remédier. Abonné à Ben's Bites — un digest IA quotidien en anglais — il s'est désabonné au bout de quelques mois. Il attribue cet abandon à un manque de discipline. **C'est une lecture erronée, et la corriger est le fondement de tout le produit** : ses podcasts, eux, demandent plusieurs heures d'écoute par semaine contre cinq minutes de lecture quotidienne, et ils n'ont jamais sauté. La discipline n'est pas en cause.

La différence réelle est l'ancrage. Le podcast se greffe sur un moment qui existait déjà — le trajet, la marche — et ne réclame aucune plage d'attention nouvelle. La newsletter exigeait qu'un moment soit créé chaque jour. Un moment qu'il faut créer finit toujours par ne pas l'être.

Le coût du statu quo est daté : en novembre, il devra entrer sur le marché en le découvrant. Chaque semaine sans signal fiable est une semaine où il progresse peut-être dans la mauvaise direction.

## La solution

Une page web unique, à URL fixe, régénérée chaque nuit. Un seul favori sur le téléphone ; la page est à jour au réveil, sans rien à lancer.

Trois capacités la distinguent d'un simple agrégateur :

**Aiguiller plutôt que résumer.** Chaque item porte une accroche — assez pour comprendre l'enjeu et décider si ça vaut le détour, pas assez pour se substituer à la lecture. Chaque item cite sa source et pointe vers l'original. La page est une couche de routage vers le contenu, jamais un remplacement. Elle recommande explicitement ce qui mérite le détour : « celui-là, écoute-le ».

**Couvrir large.** IA, data et informatique en général, en français comme en anglais, tous formats confondus : podcasts, newsletters, articles, publications de recherche, blogs d'ingénierie, communautés, vidéo. Le socle de sources est établi par cartographie de l'écosystème, pas par reprise des abonnements existants.

**Découvrir de nouvelles sources.** Périodiquement, l'agent propose des sources hors du socle initial. La veille s'élargit avec le temps au lieu de tourner en rond — c'est ce qui la distingue d'une liste de favoris.

### Trois registres, trois quotas

La page est structurée en sections à quotas fixes, pour qu'aucun registre n'écrase les autres :

| Section | Quota | Contenu |
|---|---|---|
| **Apprendre** | ~3 items | Technique : papiers accessibles, tutoriels, retours d'ingénierie, nouveautés d'outils |
| **Ce qui bouge** | ~3 items | Actualité : sorties de modèles, annonces des laboratoires, débats du secteur |
| **Pour le métier** | ~2 items | Marché : compétences demandées, compétitions Kaggle, ce qui revient dans les offres |

Ce découpage règle le conflit entre progresser, suivre le rythme et rester employable : les trois sont servis chaque jour, dans des proportions décidées à l'avance plutôt que laissées au hasard du flux. Les quotas sont ajustables à l'usage.

## Ce que ça change vraiment

Pas de moat technique, et il serait malhonnête d'en inventer un : les briques sont des flux RSS et des API publiques.

L'avantage est ailleurs, et il est réel. **Le créneau est vacant** : « Le Fil IA », seul format quotidien court en français, est en pause depuis juin 2026. Et surtout, aucun produit existant n'est calibré sur un profil précis — les digests généralistes servent tout le monde et donc personne en particulier. C'est un outil taillé pour un seul lecteur, qui filtre selon ses objectifs à lui : c'est sa force, pas sa limite.

## Qui c'est servi

**Utilisateur unique en v1 : Abdoulaye.** Aucun multi-utilisateur, aucun compte, aucune interface d'administration.

L'architecture reste néanmoins orientable : le profil qui pilote le filtrage est une donnée d'entrée, pas du code en dur. Si le produit s'avère utile, l'ouvrir à d'autres profils est une évolution, pas une réécriture.

## Critères de succès

Le seul critère qui compte vraiment est celui de la durée. Tout le reste en découle.

| Critère | Cible |
|---|---|
| **Non-abandon** | Page encore consultée après 6 semaines — le seuil où Ben's Bites avait déjà décroché |
| Disponibilité | Page à jour avant 7h30, 7 jours sur 7, sans action de l'utilisateur |
| Temps de lecture | Sous 5 minutes pour parcourir l'ensemble |
| Actionnabilité | Au moins un item par jour donne envie d'aller lire ou écouter l'original |
| Découverte | Au moins une nouvelle source pertinente proposée par mois |
| Coût | 0 € par mois |

## Périmètre

**Dans la v1**
- Collecte large sur l'IA, la data et l'informatique : podcasts, newsletters, actualité, publications de recherche, blogs de laboratoires et d'ingénierie, communautés — en français et en anglais
- Socle de sources issu d'une cartographie de l'écosystème, pas des seuls abonnements existants
- Synthèse rédigée en français, quelle que soit la langue de la source
- Page HTML publiée en Artefact, à URL stable, lisible sur mobile
- Archive Markdown versionnée dans le dépôt
- Génération nocturne automatique
- Découverte périodique de nouvelles sources

**Hors périmètre, explicitement**
- **Agent de recherche d'emploi** — abandonné le 2026-07-23. Le besoin sera traité en mode assisté, sans système dédié
- **Digest audio** — reporté faute de matériel et de budget. Réévaluable en v2 (Kokoro tourne sur processeur seul, gratuitement)
- Envoi par email
- Multi-utilisateur
- Transcription intégrale des podcasts (coût de calcul disproportionné en v1)

## Risques et limites assumées

**Risque n°1 — l'abandon.** Le format retenu est celui-là même qui a échoué avec Ben's Bites. Le choix du texte est justifié par des contraintes réelles (pas de matériel pour l'audio, pas de budget), mais il ne résout pas le problème d'ancrage : une page web est un moment à créer. Atténuations retenues : brièveté stricte, format d'accroche plutôt que de résumé, disponibilité garantie au réveil. **À mesurer honnêtement à 6 semaines.** Si la page n'est plus ouverte, le diagnostic sera l'ancrage, pas la discipline — et il faudra revenir à l'audio.

**Risque n°2 — le bruit.** L'élargissement du périmètre multiplie le volume d'entrée par un ordre de grandeur. arXiv seul produit des dizaines de publications par jour, Hacker News des centaines d'items. Sans filtrage agressif, la page devient illisible et l'abandon devient certain — le remède au premier risque deviendrait la cause du second. Le filtrage n'est donc pas un réglage secondaire, **c'est la fonction centrale du produit**. Signaux retenus : votes communautaires (Hugging Face Daily Papers), pertinence par rapport au profil, et plafond dur d'items par section.

**Génération la veille au soir, jamais le matin.** Générer à l'aube crée une course contre la montre : une source lente ou un réseau capricieux, et la page manque au moment précis où elle est attendue. Générer la nuit laisse une dizaine d'heures de reprise. Un digest auquel on ne peut pas se fier cesse d'être ouvert.

**Qualité des synthèses non démontrée.** Une accroche qui rate son objet est pire qu'un titre brut : elle fait perdre du temps et érode la confiance. À éprouver tôt sur des cas réels.

**Les sources pourrissent, et silencieusement.** Un code HTTP 200 ne prouve rien : des flux répondent normalement en servant des dates factices ou zéro article, et les annuaires se contredisent entre eux. Deux mécanismes sont donc indispensables dès la v1 — un **contrôle de fraîcheur** (alerte si le dernier item dépasse 30 jours, ou si plusieurs items partagent la même date à la minute près) et une **mise en sommeil automatique** des sources silencieuses depuis plusieurs mois. Sans cela, la liste se dégrade sans que rien ne le signale : le pire mode de panne pour un outil de veille.

**Dépendance à des miroirs communautaires.** Plusieurs sources majeures — Anthropic, Mistral, Cohere — n'exposent aucun flux officiel et passent par des dépôts tiers. Ces miroirs peuvent être abandonnés du jour au lendemain. Prévoir un scraper de secours sur les pages d'origine.

## Vision

À un an, l'archive Markdown devient une base de connaissances personnelle cherchable — non pas ce qui s'est passé dans l'IA, mais ce qu'Abdoulaye a réellement suivi et retenu.

À deux ou trois ans, si le produit tient dans la durée pour un lecteur, il tiendra pour d'autres. Un junior qui veut suivre un domaine où il se publie chaque jour plus que ce qu'on peut lire en un mois : le besoin n'est pas propre à une seule personne. Mais cette ouverture se mérite — elle viendra après la preuve d'usage, pas avant.
