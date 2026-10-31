# Inès · animatrice en direct

> « Je veux brancher BUTT à 19 h 58 et parler à 20 h. Pas chercher pourquoi ça refuse. »

Persona principal. Dans la console : rôle **Animateur**, avec l'interrupteur **Peut passer en direct**.

## Qui elle est

- **34 ans**, professeure des écoles.
- **Bénévole depuis trois ans.** Elle anime « Les Heures bleues », le jeudi de 20 h à 21 h, en direct.
- **Depuis chez elle**, presque toujours. Au studio une fois par trimestre.
- **Son matériel** : un ordinateur portable avec BUTT, une petite interface audio, un micro. Son téléphone posé à côté, ouvert sur la console.
- **À l'aise** avec un ordinateur et les applications. **Pas à l'aise** avec les adresses, les ports, Icecast et le vocabulaire du son.
- **Son temps** : deux heures de préparation par semaine, plus l'émission.

Inès a appris BUTT avec une vidéo. Elle a réglé son encodeur une fois, avec l'aide d'Hélène, et n'y touche plus. Ce qui compte pour elle, c'est l'heure : à 20 h, elle est à l'antenne, ou elle ne l'est pas.

## Ce qu'elle veut

- Prendre l'antenne à l'heure, sans stress, et savoir que son son part bien.
- Que son émission porte son nom à l'antenne, pour les auditeurs comme pour le site de la radio.
- Que personne d'autre ne prenne son créneau.
- Rendre l'antenne sans y penser.
- Plus tard, retrouver son émission enregistrée, pour en faire un podcast.

## Ce qui la freine

- Sept réglages d'encodeur à recopier sans faute.
- Un refus sans raison : pendant son créneau, le panneau reste sur « En attente », et rien ne dit pourquoi.
- Le jeton d'encodeur, montré une seule fois. Perdu, il faut en créer un autre, et le recopier.
- Aucun moyen d'essayer avant l'émission : un encodeur accepté prend l'antenne.
- L'entrée et la sortie du direct en coupe franche, sans fondu.

## Son parcours

1. **Une fois.** Hélène crée son compte, avec **Peut passer en direct**. Nadia le choisit dans son émission hebdomadaire, en **Compte du plateau** (**Programmation → Semaine**).
2. **Une fois.** Dans **Réglages → Mon compte**, Inès voit ses **Créneaux**. Elle crée son **Jeton d'encodeur** et le colle aussitôt dans BUTT, comme mot de passe.
3. **Chaque jeudi.** Sur la page **Antenne**, **Passer en direct** donne l'adresse, le port, le mount et l'identifiant, chacun à copier, et dit si l'encodeur est branché. Inès lance BUTT à 20 h.
4. La console affiche **Direct** et le temps écoulé. Son émission hebdomadaire donne son nom au direct : à l'antenne, le titre devient « Les Heures bleues ». **Renommer** lui en donne un autre, le temps de ce direct.
5. À 21 h, elle coupe BUTT. Les files de l'auto-DJ sont vidées, et la grille reprend sur un morceau entier.

Le détail est dans [passer-en-direct.md](../exploitation/passer-en-direct.md).

## Le moment qui compte

Jeudi, 20 h 01. BUTT tourne, mais le panneau reste sur **En attente** : « Un créneau est ouvert, l’encodeur n’est pas là. » La grille joue toujours : pas de silence. Inès vérifie son identifiant, puis se souvient : la semaine dernière, elle a renouvelé son jeton depuis son téléphone, sans le recopier dans BUTT, qui garde l'ancien. Elle crée un nouveau jeton, le colle, et passe à l'antenne à 20 h 06.

Entre-temps, au bout de 90 s, le moteur a levé l'alerte `live_absent`. La raison du refus, elle, n'était écrite que dans `playout.log`, sur la machine, que seul Karim lit.

## Ce que BUTTON fait déjà pour elle

- Les réglages de l'encodeur sont prêts à copier, un par un, dans **Passer en direct**.
- Le mot de passe de son compte ne quitte plus la console : l'encodeur a son propre jeton, qui n'ouvre que le direct.
- Son créneau est à elle. Dès qu'une émission nomme un animateur, chacun ne passe que pendant le sien. Un direct daté de l'Agenda s'ouvre 15 min avant son début.
- En retard, elle ne laisse pas de silence : l'horloge continue, et une alerte part au bout de 90 s.
- À la fin, rien à faire : la grille reprend seule.
- Les essais de connexion sont limités par adresse, jamais par compte : personne ne peut bloquer le sien juste avant son émission ([ADR 0013](../decisions/0013-bloquer-l-adresse-jamais-le-compte.md)).

## Ce qui coince encore

- **Pas d'essai hors antenne.** Le direct passe devant tout le reste. Besoin sans fiche : voir [README.md](README.md#les-besoins-sans-fiche).
- **La raison d'un refus reste cachée** : identifiant, jeton, interrupteur ou créneau, la console ne dit pas lequel. Besoin sans fiche.
- **Le panneau parle encore du « droit Stream »**, et non de l'interrupteur « Peut passer en direct ».
- **Coupe franche** à l'entrée et à la sortie du direct : les transitions de `fallback` sont cassées dans Liquidsoap 2.4 ([savonet/liquidsoap#4179](https://github.com/savonet/liquidsoap/issues/4179)).
- **Le panneau suit `brand.json`**, pas encore les réglages de la station : GEN-02, en [P1](../feuille-de-route/P1-mise-en-prod.md).
- **Pas d'enregistrement de son direct** : FON-06. **Pas de direct depuis le navigateur**, sans BUTT : FON-05. Les deux en [P3](../feuille-de-route/P3.md).

## Concevoir pour elle

- Un refus dit sa raison, et ce qu'elle peut faire seule.
- Un réglage se copie en un geste, et se comprend sans connaître Icecast.
- L'état du direct se lit de loin, sur un téléphone posé à côté du micro.
- Un geste qui coupe quelque chose, comme renouveler un jeton, dit ce qu'il coupe avant.
- La console parle de l'interrupteur « Peut passer en direct », jamais du droit `stream`.
