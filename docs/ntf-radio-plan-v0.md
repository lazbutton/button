# New Trad Fest Radio — plan V0

Sep 27, 2026 · @LAZ

Le plan de construction de la NTF Radio, sans code. Sept chantiers, deux lignes d'arrivée : le flux en ligne au Creative Camp de novembre, l'antenne en direct au NTF#4 en mai 2027. Il s'appuie sur la phase 0 de BUTTON appliquée à une seule radio, pour 50 à 85 h de travail. Il complète le doc [New Trad Fest Radio — V0](https://claude.ai/code/artifact/7474bfac-9888-4fd4-98d6-5f1b0a8b08af), qui décrit le quoi ; ici, c'est le comment.

## Ce qu'on réutilise

La V0 ne repart pas de zéro : le socle de la phase 0 est déjà en place (lots L0 à L2). On ne le refait pas.

- BUTTON tourne sur Nasgul : grille, automation, banque musicale
- VPS-1 en frontal : Debian, pare-feu, Docker, Caddy, Icecast
- HTTPS et adresses publiques (`gabbler.band`, `radio.lazbutton.xyz`), certificats renouvelés seuls
- Sécurité de base : connexions limitées, ports fermés au scan, secrets hors dépôt
- Le player HTTPS de BUTTON, déjà testé sur mobile

Reste à faire : les sept chantiers ci-dessous, du branchement du flux jusqu'au direct. Plusieurs s'appuient sur des lots de la phase 0 (L3 fondus, L4 direct), appliqués à une seule radio — pas de double compte.

## Les chantiers — flux, habillage, app, direct

Chaque chantier porte une charge et un test de fin. La case « Fini quand » le clôt : tant qu'elle n'est pas verte, le chantier n'est pas fini.

### C1 · Brancher le flux sur le collectif — 6–10 h

Objectif : le flux NTF sort en 24/7 là où le collectif écoute déjà.

- [ ] Confirmer l'hébergement : SOURCE de BUTTON vers l'Icecast du collectif (`streams.labomedia.org`), VPS-1 en secours
- [ ] Caler avec Olmo (P-Node) l'URL source, le mount et le format pour le relais 24/7
- [ ] Faire tourner le flux 48 h d'affilée, relever les silences
- [x] Page d'écoute simple, titre en cours, intégrable sur le site du NTF — `https://flux.gabbler.band/ntf/`, bouton sur `button.mp3`, titre depuis `now.json` (27 septembre 2026)

**Fini quand** le flux tient 48 h sans silence et s'écoute depuis le site du NTF.

### C2 · Habillage et grille festival — 8–14 h

Objectif : le flux sonne comme le festival, sans intervention.

- [x] Charger l'habillage du Creative Camp (jingles, virgules) comme carts — carts Jingles et Virgules, trois tons `REMPLACANT` chacun. Les vrais fichiers du camp les remplacent.
- [x] Deux horloges préréglées : rotation habillée le jour, nappe plus longue la nuit — `Jour habillé` (jingle + 3 titres, ancre dure à :00) de 7 h à minuit, `Nuit nappe` (virgule + 6 titres, ancre molle à :00) de minuit à 7 h. Commande `radiotomate ntf-grille`.
- [x] Remplir la banque avec la matière commune : archives des éditions 1 à 3 — dossiers `20-archives/ntf1` à `ntf3`, deux tons `REMPLACANT` par édition. Catégorie Archives NTF, repli sur la rotation si Beets n'a pas encore indexé.
- [x] Régler les fondus sur la file auto-DJ, ancres à l'heure — fondu 3 s sur `autodj_queue` ; ancre dure le jour, molle la nuit. Pas encore à l'antenne : Nasgul tire encore `RC_WEB_RADIO`.

**Fini quand** 24 h de flux passent sans blanc ni raccord brutal, habillage en place. Pas encore : les sons sont des remplaçants, et la grille n'est posée que sur le banc local (`radio_data`), pas sur Nasgul.

### C3 · Simplifier l'app — 6–10 h

Objectif : deux écrans, pilotables par un non-tech.

- [x] Masquer le Hub Projets et le Catalogue séparé (recherche gardée dans la console) — la console n’a pas ces écrans ; la recherche de la banque est sur Antenne
- [x] Réduire le bandeau santé à silence et auditeurs, plus l'état du direct — pastilles Silence, Auditeurs, Direct pour l’animateur
- [x] Deux rôles : admin pour toi, animateur sur son créneau — menu Antenne et Conducteur ; Carts, Auto-DJ, Paramètres et le casque interne restent à l’admin. Le créneau harbor est en C4
- [x] Cacher les réglages propres à la plateforme (multi-stations, AAC, quotas…) — Paramètres et les routes d’admin renvoient l’animateur vers Antenne

**Fini quand** un animateur pilote une émission depuis la seule console. Pas encore : le banc local a montré les deux écrans, sans pad (carts vides, catalogue en erreur), et cette console n’est pas redéployée sur `gabbler.band`.

### C4 · Le direct — 12–20 h

Objectif : un plateau entre et sort proprement.

- [ ] Brancher un vrai encodeur sur le harbor (BUTT puis Mixxx), suivre `live-qg.md`
- [x] Un identifiant par animateur, valable sur son seul créneau — champ sur l’émission (Auto-DJ), contrôle au harbor. Tant qu’aucun créneau n’est nominatif, les comptes stream actuels passent. Schéma `v15`, pas encore migré sur Nasgul
- [x] Retour à la grille sans couper un titre (EF-07), filet si l'encodeur manque (EF-01) — vidage jingles + auto-DJ et saut du titre en cours au décrochage ; alerte `live_absent` après 90 s, l’horloge continue. Tests unitaires, pas un direct réel
- [ ] Éprouver une coupure réseau de 30 s pendant un direct
- [x] Fiche « passer en direct », une page — [`passer-en-direct.md`](passer-en-direct.md)

**Fini quand** trois directs d'une heure passent sans intervention.

### C5 · Cloud partagé et archives — 8–14 h

Objectif : le collectif dépose et récupère sans toi.

- [x] Monter le Nextcloud partagé (docs et programmes) — déjà le stockage externe Nasgul sur la banque BUTTON (`BUTTON Media`). Pas un second nuage
- [x] Un dossier synchronisé qui alimente la banque de BUTTON, sans ressaisie — `00-inbox/rotation` et `00-inbox/archives/ntfN` sont promus à chaque tour du conteneur dropbox. Actif sur Nasgul à la prochaine recréation de ce conteneur depuis `ntr-ops`
- [ ] Déposer les archives des éditions 1 à 3 — les dossiers existent, les fichiers sont encore des tons `REMPLACANT`
- [x] Fiche courte : comment déposer un programme — [`deposer-un-programme.md`](deposer-un-programme.md)

**Fini quand** un programme déposé dans le cloud passe en rotation sans ton intervention. Pas encore observé sur Nasgul.

### C6 · Décrochages — 6–10 h

Objectif : le flux se partage avec les radios partenaires, dans les deux sens. Le mode d’emploi du mécanisme déjà en place est dans [`decrochage.md`](decrochage.md).

- [ ] Relais entrant : la NTF Radio relaie un plateau partenaire sur un créneau
- [ ] Relais sortant : un partenaire prend le flux NTF (la priorité relais existe déjà dans BUTTON)
- [ ] Tester un décrochage dans les deux sens avec Studio Zef ou Radio Campus
- [ ] Caler la diffusion continue 24/7 chez P-Node

**Fini quand** un décrochage programmé bascule proprement dans les deux sens.

### C7 · Filet minimal — 5–8 h

Objectif : être prévenu et pouvoir revenir en arrière, sans la machinerie de la plateforme.

- [ ] Une sonde Uptime Kuma sur le flux, alerte silence vers toi
- [ ] Une sauvegarde simple hors OVHcloud : config et banque — la copie locale `backup-radiotomate.sh` existe ; elle ne quitte pas la machine
- [x] Fiche « le flux est tombé » : quoi vérifier, comment relancer — [`le-flux-est-tombe.md`](le-flux-est-tombe.md)

**Fini quand** une coupure volontaire déclenche l'alerte en moins de 2 min et se relève en moins de 5 min.

Les sept chantiers pèsent **50 à 85 h** en tout, moitié moins que la phase 0 complète : la V0 ne construit qu'une seule radio.

## Deux lignes d'arrivée

Deux échéances commandent l'ordre. Le flux et son habillage doivent être prêts pour le Creative Camp de novembre ; le direct et les décrochages pour le NTF#4 de mai.

| Chantier | Ligne d'arrivée | Charge |
| --- | --- | --- |
| C1 · Flux sur le collectif | Creative Camp (13 nov. 2026) | 6–10 h |
| C2 · Habillage et grille | Creative Camp | 8–14 h |
| C3 · Simplifier l'app | Creative Camp | 6–10 h |
| C5 · Cloud partagé | Creative Camp (démarrage) | 8–14 h |
| C4 · Le direct | NTF#4 (5–9 mai 2027) | 12–20 h |
| C6 · Décrochages | NTF#4 | 6–10 h |
| C7 · Filet minimal | NTF#4 | 5–8 h |

Le premier bloc (C1 à C3, C5 lancé) doit tenir avant le 13 novembre : c'est là que le flux passe en ligne et que la soirée test diffuse sur les radios partenaires. Le reste court jusqu'au festival, en passant par les soirées du 26 février et du 13 mars. Le détail des temps forts est dans le doc [New Trad Fest Radio — V0](https://claude.ai/code/artifact/7474bfac-9888-4fd4-98d6-5f1b0a8b08af).

## C'est prêt quand

La recette est chiffrée, pas au ressenti. Deux jalons, un par ligne d'arrivée.

**Prêt pour le Creative Camp — 13 novembre 2026**

- le flux 24/7 tient 48 h d'affilée sans silence
- la soirée test diffuse en simultané sur les radios partenaires
- l'app se pilote depuis un seul écran

**Prêt pour le NTF#4 — 5 mai 2027**

- trois directs d'une heure passent sans intervention
- un décrochage a été testé dans les deux sens avec un partenaire
- une coupure de flux se relève en moins de 5 min
- la banque tourne sur la matière commune déposée dans le cloud

## À côté du dev

Ces actions ne sont pas du code mais conditionnent la V0. Aucune n'attend décembre.

| Action | Avec qui | Quand |
| --- | --- | --- |
| Confirmer l'hébergement du flux | Radio Campus / Labomedia | avant le Creative Camp |
| Caler le relais 24/7 (URL source, format) | Olmo (P-Node) | octobre |
| Récupérer les archives des éditions 1 à 3 | les trois radios | sept.–oct. |
| Fixer le nom et l'habillage | le collectif | Creative Camp (13–14 nov.) |
| Désigner la radio éditrice, déclarer SACEM et SPRE | Radio Campus, Zam Zam | avant le flux public |
| Décider qui administre le Nextcloud commun | le collectif | avant C5 |

## Si ça dérape

L'ordre des replis est décidé d'avance, chantier par chantier. Les partiels de droit peuvent aussi manger des semaines.

- **Hébergement collectif pas prêt (C1)** — diffuser depuis le VPS-1, relayé à P-Node ; on bascule sur l'Icecast du collectif après le camp
- **Habillage en retard (C2)** — jingles minimaux pour le camp, on enrichit ensuite
- **Direct instable (C4)** — grille seule et captations diffusées en différé ; on garde le direct pour les gros créneaux du festival
- **Cloud pas prêt (C5)** — dépôt à la main dans la banque, Nextcloud ensuite
- **Règle d'or** — ne jamais couper le flux pendant le festival ; le filet C7 (alerte et sauvegarde) n'est jamais sacrifié
