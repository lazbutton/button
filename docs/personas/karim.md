# Karim · technicien bénévole

> « Une mise à jour, ça doit pouvoir se défaire. Et je veux être prévenu avant les auditeurs. »

Persona principal. Dans la console : rôle **Admin**. Hors de la console : la machine, le dossier `deploy/` et Docker Compose.

## Qui il est

- **38 ans**, administrateur systèmes dans une PME.
- **Bénévole technique depuis cinq ans.** C'est lui qui a choisi BUTTON, et qui l'a installé.
- **Son travail à la radio** : la machine. L'installation, les mises à jour, les sauvegardes, les pannes.
- **Son matériel** : son ordinateur, un accès SSH au VPS, Tailscale, et son téléphone pour les alertes.
- **À l'aise** avec Linux, Docker, les reverse proxies et les journaux. **Pas à l'aise** avec Liquidsoap, et avec l'idée d'être le seul à savoir.
- **Son temps** : quelques soirées par mois, plus les urgences.

Karim n'est presque jamais au local. Il connaît la station par ses journaux et ses sondes. Il sait qu'il est le seul à pouvoir la réparer, et voudrait que ce ne soit plus vrai : ce qu'il fait doit tenir en une commande, ou se trouver dans la documentation.

## Ce qu'il veut

- Installer une station en peu de commandes, et la réinstaller à l'identique.
- Des mises à jour qui ne cassent pas l'antenne, et qui se défont.
- Des sauvegardes hors de la machine, déjà restaurées une fois pour de vrai.
- Être prévenu d'une panne avant qu'un auditeur n'appelle la radio.
- Une machine exposée à Internet qui reste fermée : HTTPS, ports fermés, secrets solides.
- Pouvoir passer la main.

## Ce qui le freine

- Le réseau partagé du moteur : redémarrer le playout seul rend l'interface et le scheduler injoignables.
- Une migration du schéma qui ne se défait qu'avec l'image récente, ou une copie de la base.
- Docker, qui publie ses ports par-dessus le pare-feu.
- Être appelé en pleine journée de travail, et réparer depuis son téléphone.
- Des images construites pour amd64 seulement.

## Son parcours

1. **Installer.** `git clone`, `deploy/.env` copié de l'exemple, chaque `change-me` remplacé, `docker compose up -d`. Sur un secret d'exemple, la station refuse de démarrer, et le journal de `radiotomate-init` nomme la variable : [deploiement.md](../deploiement.md).
2. **Fermer.** `BIND_ADDRESS=127.0.0.1` derrière le reverse proxy de la machine. Le dossier partagé n'écoute que sur l'adresse Tailscale : [dossier-reseau.md](../exploitation/dossier-reseau.md).
3. **Contrôler.** Depuis `deploy/`, `scripts/smoke.sh <console> <flux>` dit sans compte si l'antenne tourne, et quel journal lire au premier point qui échoue.
4. **Mettre à jour.** Une archive avec `backup-radiotomate.sh`, le nouveau `RT_TAG` dans `.env`, `docker compose up -d`, puis le contrôle. Le moteur copie lui-même la base avant chaque migration.
5. **Revenir en arrière.** L'ancien `RT_TAG`. Si le schéma a migré, le redescendre d'abord, ou remettre la copie d'avant la migration : [sauvegarde.md](../exploitation/sauvegarde.md).
6. **Réparer.** Suivre l'ordre de [le-flux-est-tombe.md](../exploitation/le-flux-est-tombe.md), et recréer les trois services du moteur ensemble.

## Le moment qui compte

Dimanche, 23 h. Karim met la station à jour. `radiotomate-init` s'arrête : une migration du schéma a échoué, et le journal dit « rolled back ». Le moteur ne démarre pas, et l'antenne est coupée. C'était la première migration due : la base n'a pas bougé. Karim remet l'ancien `RT_TAG`, relance la station, puis le contrôle. Onze minutes sans antenne.

Il aurait voulu que la mise à jour revienne seule en arrière, et le lui dise : c'est MAJ-05. Et qu'elle refuse de partir si un direct commençait dans la demi-heure : c'est MAJ-04.

## Ce que BUTTON fait déjà pour lui

- La station refuse les secrets d'exemple et les secrets trop courts, et dit lesquels.
- Une copie de la base avant chaque migration. Chaque version du schéma passe dans sa propre transaction : celle qui échoue ne laisse rien.
- `smoke.sh` contrôle l'antenne sans compte, après une installation ou une mise à jour.
- Les ports publiés écoutent sur `BIND_ADDRESS`, et la console pose ses en-têtes de sécurité.
- Les essais de connexion sont limités par adresse, dans le moteur et dans nginx. Derrière un reverse proxy, l'adresse comptée est celle du client.
- Des sondes de santé sur les trois services du moteur, des alertes vers un webhook ou Vikunja, des métriques.
- Des images taguées par date : `RT_TAG` remet le moteur et le playout à une version précise. Les autres images suivent `main` jusqu'à MAJ-01.

## Ce qui coince encore

Toute la priorité [P1](../feuille-de-route/P1-mise-en-prod.md) est écrite pour lui. Tant qu'une fiche P1 reste ouverte, une installation sur un VPS est un essai, pas une production :

- **HTTPS** par un reverse proxy : INS-01. **Installer en une commande** : INS-02. **Des commandes d'exploitation** : INS-03.
- **Des versions et un canal stable** : MAJ-01. **Une commande de mise à jour** : MAJ-04. **Un retour arrière automatique** : MAJ-05.
- **Des sauvegardes hors de la machine** : SAV-01. **Des alertes sur le téléphone et par e-mail** : SUR-01.
- **Un guide d'installation sur VPS** : DOC-01.

Puis, en [P2](../feuille-de-route/P2.md) : les mises à jour la nuit (MAJ-06), un réseau du moteur découplé (ARC-01), une sonde du flux lancée depuis une radio amie (SUR-02), un export de diagnostic à envoyer pour se faire aider (SUR-03). En [P3](../feuille-de-route/P3.md) : des images pour les VPS ARM (ARC-04).

## Concevoir pour lui

- Une commande, un résultat lisible, un code de sortie.
- Un échec nomme ce qui a échoué, et le journal à lire.
- Rien d'irréversible sans une copie d'abord.
- La documentation d'exploitation suit le code, dans la même branche.
- Ce que fait Karim, une autre personne doit pouvoir le refaire avec la documentation seule.
