# Fatou · auditrice

> « Quand j'allume, ça doit jouer. »

Persona secondaire. Fatou ne voit jamais la console, et ne sait pas que BUTTON existe. Ce qu'elle connaît, c'est l'antenne.

## Qui elle est

- **41 ans**, aide-soignante, en horaires décalés.
- **Elle écoute** le matin dans la cuisine, sur une enceinte connectée, et dans le bus, sur son téléphone, en 4G. Parfois la nuit, après une garde.
- **Depuis six ans**, depuis qu'une émission de jazz du dimanche l'a fait rester.
- **À l'aise** avec son téléphone et les applications de radio.

## Ce qu'elle veut

- Que ça joue dès qu'elle allume, à toute heure.
- Savoir ce qui passe : le titre, l'artiste, le nom de l'émission.
- Un son égal, sans titre trop fort ni trop faible.
- Retrouver une émission manquée.

## Ce qui la freine

- Le silence, qui lui fait croire que la radio a fermé.
- Le flux qui coupe dans le bus, quand le réseau faiblit.
- L'enceinte qui s'arrête quand le flux tombe, et qu'il faut relancer.
- Un titre affiché qui n'est pas celui qu'elle entend.

## Le moment qui compte

Dimanche, 23 h, après une garde. Fatou écoute l'émission de nuit quand le son s'arrête : Karim met la station à jour, et une migration a échoué. L'enceinte attend un moment, puis se tait pour de bon. Fatou ne la relance pas : elle croit que la radio a fermé pour la nuit.

## Ce que BUTTON fait déjà pour elle

- Une grille qui tient 24 h sur 24, la nuit aussi, sans personne au studio.
- Une alerte quand l'antenne se tait, pour que quelqu'un réagisse.
- Un volume égalisé (ReplayGain), et des fondus de 3 s entre les titres de l'auto-DJ.
- Le titre en cours, publié dans `now.json` pour le site et les lecteurs. Pendant un direct, le nom de l'émission.

## Ce qui coince encore

- **Une mise à jour coupe le flux**, et Icecast déconnecte ses auditeurs : selon son lecteur, Fatou doit relancer la radio. MAJ-08, en [P2](../feuille-de-route/P2.md), doit les garder connectés.
- **Un flux en MP3.** Un flux AAC, puis HLS, demanderait moins de débit et tiendrait mieux sur les réseaux mobiles : FON-04, en [P3](../feuille-de-route/P3.md).
- **Pas de podcasts des directs** : FON-06. **Pas de lecteur à poser sur le site de la radio** : FON-02. Les deux en P3.
- **Une panne vue de l'extérieur** : une sonde du flux, lancée d'une autre machine, préviendrait même si toute la machine tombe : SUR-02, en P2.

## Concevoir pour elle

- L'antenne ne se tait jamais. Une fonction nouvelle se demande ce qu'elle fait au son quand elle échoue.
- Ce qui se passe sur la machine se mesure aussi du côté de l'auditrice : pendant une mise à jour, une panne, un direct qui commence.
