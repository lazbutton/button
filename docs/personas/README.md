# Personas

Les personnes pour qui BUTTON est fait. Ce sont des personnages inventés. Ce qu'ils font dans BUTTON vient du code et de la documentation : les rôles, les écrans, les messages, les limites. Le reste, leur vie, leur aisance, ce qu'ils pensent, sont des hypothèses sur les radios associatives, à vérifier auprès de vraies équipes : voir [plus bas](#ce-qui-reste-à-vérifier).

## À quoi ils servent

- **Trancher une question de produit.** Pour qui est ce changement ? Jean-Pierre comprendrait-il ce message ? Lou y arriverait-elle depuis son téléphone ?
- **Écrire une fiche.** Son « Pourquoi » peut nommer le persona qu'elle sert.
- **Relire un écran.** Le parcourir avec les yeux de chacun de ceux qui l'ouvrent.

## Les personas

| Persona | En une phrase | Dans BUTTON |
|---|---|---|
| [Inès, animatrice en direct](ines.md) | Anime son émission du jeudi soir depuis chez elle, avec BUTT | Animateur, avec « Peut passer en direct » |
| [Jean-Pierre, bénévole de permanence](jean-pierre.md) | Surveille l'antenne au studio deux après-midi par semaine, et passe les dédicaces | Animateur |
| [Nadia, programmatrice](nadia.md) | Fait sonner la radio 24 h sur 24 : grille, sélections, habillage, invités | Programmateur |
| [Hélène, coordinatrice](helene.md) | Fait tourner l'association : l'équipe, les comptes, l'identité de la station | Admin |
| [Karim, technicien bénévole](karim.md) | A installé la station sur un petit VPS, et la maintient le soir | Admin, et la machine |
| [Lou, DJ invitée](lou.md) | Dépose un set par mois depuis Montréal, par un lien, sans compte | Invitée, sans compte |
| [Fatou, auditrice](fatou.md) | Écoute la radio chaque jour, sans savoir que BUTTON existe | Ne voit jamais la console |

Les six premiers se servent de BUTTON. Fatou est un persona secondaire : elle n'ouvre jamais la console, mais c'est pour elle que l'antenne tourne.

## La radio où ils vivent

Tous les sept tournent autour de la même radio, inventée elle aussi : une radio associative d'une ville moyenne, qui diffuse sur Internet. Une quarantaine de bénévoles, deux salariées, un studio au local de l'association, une trentaine d'émissions par semaine. La station tourne sur un petit VPS, et l'auto-DJ tient l'antenne entre les émissions.

## Qui fait quoi

| Ce qu'il faut faire | Qui | Où |
|---|---|---|
| Tenir l'antenne : suivant, file, dédicace, jingle | Jean-Pierre, et tout compte | **Antenne**, le pupitre |
| Passer en direct | Inès | **Antenne → Passer en direct** : [passer-en-direct.md](../exploitation/passer-en-direct.md) |
| Déposer de la musique ou de l'habillage | Nadia | **Sons → Banque**, ou le dossier de la station : [deposer-un-programme.md](../exploitation/deposer-un-programme.md) |
| Composer les heures types et la semaine | Nadia | **Programmation → Heures types**, **Semaine**, **Sélections de titres** |
| Préparer les bacs, les relais, un décrochage | Nadia | **Sons → Bacs** : [decrochage.md](../exploitation/decrochage.md) |
| Inviter un DJ | Nadia | **Programmation → Agenda** : [inviter-un-dj.md](../exploitation/inviter-un-dj.md) |
| Déposer un set | Lou | Sa page, ouverte par son lien privé |
| Créer, changer, supprimer un compte | Hélène | **Réglages → Comptes** |
| Régler le nom, l'accroche, le flux public | Hélène | **Réglages → Station** |
| Installer, mettre à jour, sauvegarder | Karim | `deploy/` : [deploiement.md](../deploiement.md), [sauvegarde.md](../exploitation/sauvegarde.md) |
| Réagir à une panne | Jean-Pierre la voit, Karim la répare | La pastille d'état, puis [le-flux-est-tombe.md](../exploitation/le-flux-est-tombe.md) |
| Écouter | Fatou | Le flux public, et `now.json` pour le titre |

## Une semaine à la radio

- **Lundi.** Nadia dépose les nouveautés, puis pose dans l'Agenda le set de Lou, samedi à 22 h. Elle copie le message, avec le lien, et l'envoie à Lou.
- **Mardi.** Pendant la permanence de Jean-Pierre, la pastille passe à « Silence 8 s ». Il appuie sur **Suivant**, et le son revient.
- **Mercredi.** Hélène crée les comptes de trois nouveaux bénévoles. L'un d'eux aura une émission en direct : elle allume **Peut passer en direct**.
- **Jeudi.** À 20 h, l'encodeur d'Inès est refusé : il garde un ancien jeton. Elle en crée un nouveau, et passe à l'antenne à 20 h 06. À 21 h, elle coupe, et la grille reprend.
- **Vendredi.** Lou dépose son set depuis un café de Montréal, sans cocher ses droits. **À préparer** le signale à Nadia, qui la relance.
- **Samedi.** Le set de Lou passe à 22 h, en entier.
- **Dimanche.** Karim met la station à jour. Une migration échoue, et l'antenne se coupe onze minutes. Fatou, qui écoutait, croit que la radio a fermé pour la nuit.

## Ce qu'ils ont en commun

- **Peu de temps, pas de formation.** La plupart sont bénévoles. Ils apprennent BUTTON seuls, ou d'un collègue, en quelques minutes. L'interface parle la langue de la radio, en français : [ADR 0012](../decisions/0012-l-interface-est-en-francais.md), [glossaire](../glossaire.md).
- **L'antenne avant tout.** Un écran peut attendre, pas l'antenne. La grille tient seule, et reprend seule après un direct ou un set.
- **Jamais d'échec silencieux.** Chacun doit savoir ce qui se passe, ce que ça change pour les auditeurs, et quoi faire. La règle est dans [console/AGENTS.md](../../console/AGENTS.md).
- **Pas toujours devant un grand écran.** Inès suit son direct sur son téléphone, Lou dépose parfois depuis le sien, Hélène crée un compte entre deux réunions. La console tient sur téléphone, au clavier, en clair et en sombre.
- **Des rôles simples.** Trois rôles et un interrupteur, jamais les six droits du moteur : [api.md](../api.md#rôles-et-droits).
- **Personne ne touche la machine depuis la console.** Ce qui touche Docker reste à Karim, ou passe par une demande que la machine exécute : [ADR 0004](../decisions/0004-la-console-ne-pilote-jamais-docker.md).

## Pas pour l'instant

BUTTON ne vise pas encore :

- **plusieurs stations sur une machine** : une machine porte une station, [ADR 0002](../decisions/0002-une-station-par-machine.md) ;
- **une station hors du fuseau de Paris** : une vingtaine de fichiers du moteur dépendent de l'heure locale, ARC-02 en [P3](../feuille-de-route/P3.md) ;
- **une équipe qui ne lit pas le français** : la traduction viendra, d'abord en anglais, FON-09 en [P3](../feuille-de-route/P3.md).

## Les besoins sans fiche

Quelques besoins sont apparus en écrivant ces pages, qu'aucune fiche de la [feuille de route](../feuille-de-route/README.md) ne couvre. Ce sont des questions de produit, pas des décisions.

| Besoin | Pour | Aujourd'hui |
|---|---|---|
| Essayer son encodeur hors antenne | Inès | Le direct passe devant tout le reste : un encodeur accepté prend l'antenne |
| Voir dans la console pourquoi un encodeur est refusé | Inès, Hélène | Pendant le créneau, le panneau reste sur « En attente ». La raison n'est écrite que dans `playout.log`, sur la machine |
| Nommer l'animateur d'une émission sans être admin | Nadia | Le champ « Compte du plateau » ne liste les comptes que pour un admin |
| Savoir qui prévenir quand l'automate ne répond plus | Jean-Pierre | Le bandeau dit depuis quand l'automate se tait, pas à qui le dire |
| Rappeler sa date limite à un invité | Lou, Nadia | **À préparer** liste ce qui manque, mais la relance se fait à la main |

Une question tranchée devient une fiche, dans la bonne page de la feuille de route, et quitte ce tableau.

## Ce qui reste à vérifier

Ces personas n'ont pas encore rencontré de vraies équipes. Les hypothèses à vérifier d'abord :

- la part des directs faits depuis chez soi, et depuis le studio ;
- l'âge des bénévoles, et leur aisance avec un ordinateur ou un téléphone ;
- le nombre d'invités par mois, et d'où ils déposent ;
- qui maintient la machine : un bénévole seul, une petite équipe, un prestataire ;
- dans une petite radio, si la coordinatrice et le technicien sont une seule personne ;
- comment les auditeurs écoutent : le site, une application, une enceinte connectée.

Un entretien qui confirme ou dément une hypothèse se note dans la page du persona, sans nom de station ni de personne réelle.

## Faire vivre ces pages

Comme le reste de la documentation, ces pages suivent le code. Une fiche qui change ce qu'un persona fait met sa page à jour dans la même branche : ce qu'elle apporte passe de « Ce qui coince encore » à « Ce que BUTTON fait déjà ».
