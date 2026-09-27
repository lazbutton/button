# Plan de développement — phase 0

Sep 27, 2026 · @LAZ

La phase 0 tient en six sprints de deux semaines, du 28 septembre au 20 décembre 2026, pour 96 à 165 h de travail. La première radio bêta arrive le 7 décembre, et le critère de passage se vérifie le 15 janvier 2027.

Chaque lot dit ce qu'il faut construire et à quoi on reconnaît qu'il est fini ; aucune ligne de code. Le plan découle du doc [Business model de l'automate BUTTON](https://claude.ai/code/artifact/978701ac-52e6-40d2-a1b7-0c4961139071).

## Périmètre

La phase 0 rend l'automate utilisable par une radio extérieure, sans que tu interviennes chaque semaine. Tout ce qui sert à vendre ou à se différencier attend la phase 1.

**Dans la phase 0**

- HTTPS et adresses publiques, sans Tailscale
- Sécurité de l'accès public
- Fondus enchaînés
- Live de bout en bout, avec un compte par DJ
- Dépôt de musique par le navigateur
- Stations créées par script, isolées les unes des autres
- Alertes envoyées à la radio et page de statut
- Sauvegardes avec une restauration testée
- Mises à jour par vagues
- Kit d'accueil de la bêta

**Plus tard (phase 1 et suivantes)**

- Interface unique : pendant la bêta, les radios utilisent la console et l'UI Radiotomate actuelles, derrière HTTPS
- Paiement Stripe et CGV : la bêta est gratuite
- Site vitrine et documentation publique
- Émissions et résidents, enregistrement des lives, publication Mixcloud
- Flux AAC, relevés SACEM/SPRE, statistiques d'écoute

## Décisions à trancher au démarrage

Ces choix se font le premier jour du sprint 1. La recommandation suffit pour avancer, et aucune ne ferme de porte pour la phase 1.

| Décision | Recommandation | Pourquoi |
| --- | --- | --- |
| Serveur des stations | Kimsufi KS-5 plus tard. **Pour l’instant : VPS-1 2027** (OVHcloud) en frontal, stations sur Nasgul | le VPS-1 a 2 vCores, 4 Go de RAM et 40 Go NVMe : il publie le flux, il n’héberge pas Liquidsoap ni la banque |
| Adresses | console sur `nom.domaine.fr`, flux sur `flux.domaine.fr/nom.mp3` | Caddy obtient et renouvelle les certificats seul ; l'adresse d'un flux ne change plus une fois inscrite dans les annuaires |
| Icecast | un Icecast partagé, avec un mount et un mot de passe source par station | un seul service à exposer derrière Caddy ; quota d'auditeurs réglable par mount |
| Base de chaque station | une base SQLite par station, comme aujourd'hui | stations isolées ; sauvegarde continue par Litestream |
| Sauvegardes | Object Storage chez un autre fournisseur qu'OVHcloud | un incident chez l'hébergeur n'emporte pas les copies |
| Liquidsoap | rester en 2.4.5 toute la phase 0 | la 2.5 n'est pas publiée ; les fondus passent par un crossfade sur la file auto-DJ |
| Accès des radios | UI Radiotomate et console derrière HTTPS, un compte par personne | l'interface unifiée attend la phase 1 |
| Nom et domaine | un domaine de travail neutre, distinct de BUTTON | le nom commercial se décide plus tard sans bloquer le dev |
| Dépôts | Radiotomate est dans ce dépôt depuis le 27 septembre 2026 (accord signé). `button-console` et `button-ops` restent les clones d’à côté tant que la bascule Nasgul n’est pas faite | l'offre ne dépend plus du dépôt de l'association pour le moteur |

## Machine du moment — 27 septembre 2026

Le KS-5 n’est pas commandé. La machine publique est un **VPS-1 2027** OVHcloud : 2 vCores, 4 Go de RAM, 40 Go NVMe, trafic non mesuré, 500 Mbit/s. C’est déjà l’hôte de `radio.lazbutton.xyz` (Icecast public, edge Ondes).

| Rôle | Où, tant que le KS-5 n’est pas là |
| --- | --- |
| Liquidsoap, horloges, banque, SQLite | Nasgul |
| HTTPS, Icecast public, certificats | VPS-1 |
| Plusieurs stations avec leur musique | impossible sur 40 Go et 4 Go : ça attend le KS-5 (L6, L8) |

Le sprint 1 (L0–L2) se fait donc sur ce VPS pour l’adresse publique, sans y déplacer l’automate. La migration de BUTTON hors de Nasgul reste le lot L6, et elle ne tient pas sur le VPS-1.

## Calendrier

La phase 0 s'étale sur six sprints de deux semaines. La première radio bêta démarre le 7 décembre, une fois la migration de BUTTON bouclée au sprint 4. Le compteur de trente jours court ensuite du 21 décembre au 15 janvier.

Le tableau reprend les onze lots. L’observation et le critère de passage sont plus bas.

| Sprint | Dates | Lots | Charge |
| --- | --- | --- | --- |
| S1 | 28 sept.–11 oct. | L0, L1, L2 | 15–28 h |
| S2 | 12–25 oct. | L3, L4 | 20–40 h |
| S3 | 26 oct.–8 nov. | L5 | 15–25 h |
| S4 | 9–22 nov. | L6, migration BUTTON | 20–30 h |
| S5 | 23 nov.–6 déc. | L7, L8 | 16–24 h |
| S6 | 7–20 déc. | L9, L10, radios bêta | 10–18 h |

La capacité tient entre 16 et 24 h par sprint. Le sprint 6 sert de tampon, et le haut de la fourchette déborde sur les congés de fin d'année.

## Les lots, du socle au premier flux

Chaque lot porte une charge et un sprint. La case « Fini quand » est le test qui le clôt : tant qu'il n'est pas vert, le lot n'est pas fini.

### L0 · Socle : serveur, domaine, dépôt — 6–10 h, S1

Objectif : un serveur propre, reconstructible d'une commande.

- [x] Accord écrit sur Radiotomate — signé le 27 septembre 2026. Le moteur est dans ce dépôt (`radiotomate/`). Nasgul déploie encore depuis `RC_WEB_RADIO` tant que le pipeline n’a pas basculé.
- [ ] Créer le dépôt plateforme à partir du fork Radiotomate, de la console et des fichiers d'exploitation
- [ ] Acheter un domaine de travail neutre
- [ ] Commander le KS-5, installer Debian et un rôle Ansible : utilisateur, pare-feu, Docker, mises à jour automatiques
- [ ] Écrire la fiche « reconstruire le serveur de zéro » et la tester une fois

**Fini quand** le serveur se réinstalle depuis le dépôt en moins d'une heure.

### L1 · HTTPS et adresses publiques — 5–10 h, S1

Objectif : un flux et une console joignables en HTTPS, sans Tailscale.

- [ ] Caddy en frontal, certificats Let's Encrypt, renouvellement compris
- [ ] Schéma d'adresses arrêté (console `nom.domaine.fr`, flux `flux.domaine.fr/nom.mp3`)
- [ ] Flux Icecast servi sur 443 ; le harbor garde son port
- [ ] Vérifier le player de BUTTON sur une page HTTPS, puis sur téléphone

**Fini quand** un player HTTPS lit le flux, sur ordinateur comme sur mobile.

### L2 · Sécurité de l'accès public — 4–8 h, S1

Objectif : n'exposer que l'utile, cloisonner les radios.

- [ ] Un compte par personne, mots de passe longs
- [ ] Limiter les tentatives de connexion (Caddy ou fail2ban)
- [ ] N'exposer que les écrans nécessaires ; hub et catalogue restent internes ; seuls 443 et le harbor ouverts
- [ ] Secrets par station, hors du dépôt
- [ ] Tester l'étanchéité entre deux stations

**Fini quand** un scan ne montre que 443 et le harbor, et qu'aucun compte ne passe d'une station à l'autre.

### L3 · Fondus enchaînés — 5–15 h, S2

Objectif : des transitions douces sur l'auto-DJ, sans casser les ancres horaires. Le bug [savonet/liquidsoap#4179](https://github.com/savonet/liquidsoap/issues/4179) laisse les transitions de `fallback` en coupe ; le fondu se fait donc en amont, sur la file.

- [ ] Fondu sur la file auto-DJ, avant le `fallback`
- [ ] Durées réglées à l'oreille : environ 3 s entre titres, court ou nul vers un jingle
- [ ] Coupe franche assumée sur live ↔ automate, jusqu'à la 2.5
- [ ] Ancres dures toujours à l'heure
- [ ] Écouter 50 enchaînements sur BUTTON

**Fini quand** 50 enchaînements passent sans coupe audible et que les ancres tombent à l'heure.

### L4 · Live de bout en bout et comptes DJ — 15–25 h, S2

Objectif : un vrai direct où le DJ entre seul et revient à la grille sans accroc.

- [ ] Brancher un vrai encodeur sur le harbor en suivant `live-qg.md` : BUTT, puis Mixxx
- [ ] Un identifiant par DJ, valable seulement sur son créneau
- [ ] Retour à la grille sans reprendre un titre en cours (EF-07)
- [ ] Filet et alerte quand l'encodeur manque (EF-01)
- [ ] Éprouver une coupure réseau de 30 s pendant un direct
- [ ] Fiche « passer en direct », une page

**Fini quand** trois directs d'une heure passent sans intervention et qu'un DJ hors créneau est refusé.

### L5 · Dépôt de musique par le navigateur — 15–25 h, S3

Objectif : une radio envoie sa musique depuis un navigateur, sans toi.

- [ ] Page d'envoi reprenable (Uppy + tusd) vers l'inbox
- [ ] Promotion automatique via `promote-inbox`, conversion et ReplayGain
- [ ] Refus des formats inconnus, doublons signalés
- [ ] Avancement et rejets affichés avec leur raison
- [ ] Quota de stockage par station

**Fini quand** un album de 2 Go, envoyé en 4G, coupé puis repris, passe en rotation en moins de 10 min avec les bons tags.

### L6 · Multi-stations par script — 20–30 h, S4

Objectif : créer et isoler une station en une commande. C'est ici que BUTTON devient la première station de la plateforme.

- [ ] Modèle de station à partir des conteneurs de BUTTON, données dans un dossier par station
- [ ] Commande de création : ports, mount, route Caddy, comptes ; puis suspension sans effacement
- [ ] Limites mémoire et processeur par station
- [ ] Quota d'auditeurs par mount
- [ ] Migrer BUTTON en première station ; Nasgul reste en secours jusqu'à la fin de L8
- [ ] Test de charge : cinq stations, dont une qu'on fait planter

**Fini quand** une station naît en moins de 15 min et que la panne d'une station n'en touche aucune autre.

### L7 · Alertes et page de statut — 8–12 h, S5

Objectif : chaque radio est prévenue de ses propres pannes ; toi, des pannes de plateforme.

- [ ] Une sonde Uptime Kuma par station
- [ ] Le silence part vers Apprise, sur le canal choisi par la radio (e-mail ou messagerie)
- [ ] Tri : panne de station vers la radio, panne de plateforme vers toi
- [ ] Page de statut publique

**Fini quand** une coupure volontaire déclenche l'alerte chez la radio en moins de 2 min.

### L8 · Sauvegardes et restauration testée — 8–12 h, S5

Objectif : une station perdue revient en une heure, sur un serveur vierge.

- [ ] Litestream vers un Object Storage d'un autre fournisseur
- [ ] restic nocturne pour les médias, rétention définie
- [ ] Restauration complète d'une station sur une machine neuve
- [ ] Fiche de restauration datée

**Fini quand** une station revient en moins d'une heure ; Nasgul peut alors cesser d'héberger BUTTON.

### L9 · Mises à jour par vagues — 4–8 h, S6

Objectif : déployer sans risquer toutes les stations d'un coup.

- [ ] Adapter `nasgul-update.sh` : BUTTON d'abord, les autres une fois BUTTON saine
- [ ] Retour à l'image précédente avec `HOLD`, par station
- [ ] Gel pendant l'observation, sauf correctifs

**Fini quand** une mise à jour ratée revient seule sans toucher les autres stations.

### L10 · Kit d'accueil de la bêta — 6–10 h, S6

Objectif : une radio s'installe seule avec la doc.

- [ ] Doc courte : envoyer sa musique, régler une horloge, passer en direct, lire ses alertes
- [ ] Deux modèles d'horloges : rotation habillée et nuit
- [ ] Convention de bêta, une page : gratuité sans garantie ; SACEM et SPRE à la charge de la radio
- [ ] Point hebdomadaire de 15 min et formulaire de retour

**Fini quand** la radio bêta 2 s'installe seule avec la doc.

En tout, la phase 0 pèse **96 à 165 h**, un peu au-dessus des 100 à 150 h du business model une fois la sécurité et le kit bêta comptés.

## La recette : ce qui déclenche le passage

Le critère de passage est chiffré, pas au ressenti. Un incident, c'est l'un de ces quatre cas :

- un silence non voulu de plus de 2 min ;
- un flux injoignable plus de 5 min ;
- une perte de données ;
- une intervention manuelle pour remettre une station en route.

**Le critère** : 3 radios bêta avec 30 jours consécutifs sans incident, BUTTON non comptée. La mesure s'appuie sur l'historique Uptime Kuma et le journal des alertes ; la vérification tombe le 15 janvier 2027. Après un incident, on corrige, puis le compteur de 30 jours repart pour cette radio — pas pour les autres.

## À côté du développement

Ces tâches ne sont pas du code, mais elles conditionnent la phase 0. Aucune ne doit attendre décembre.

| Tâche | Quand |
| --- | --- |
| Accord écrit avec l'association sur ce qui, dans le dépôt, est à toi | avant le 11 octobre |
| Écrire à Martin Kirchgessner, mainteneur de Radiotomate | sprint 1 |
| Recruter 3 radios bêta : premiers contacts en octobre | engagement avant le 22 novembre |
| Choisir le nom commercial et déposer la marque (INPI, 190 €) | avant le kit bêta |
| Paris Radio Show, en visiteur | 15 décembre 2026 |

## Si le planning dérape

Les sprints S2 et S4 débordent au haut de la fourchette, et les partiels de droit tombent en plein dedans. L'ordre des sacrifices est décidé d'avance :

- Réduire L10 à la seule doc, sans les deux modèles d'horloges.
- Faire L9 à la main : déployer station par station soi-même.
- Démarrer à 2 radios bêta, la troisième en janvier ; le critère glisse d'autant.
- Ne jamais couper L7 ni L8 : sans alertes ni sauvegardes testées, une bêta n'est pas tenable.
- Garder une semaine sans dev pendant les partiels, de préférence pendant l'observation.
