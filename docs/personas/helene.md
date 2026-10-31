# Hélène · coordinatrice

> « Je dois pouvoir ouvrir un accès à un nouveau bénévole en deux minutes, et le fermer aussi vite. »

Persona principal. Dans la console : rôle **Admin**.

## Qui elle est

- **52 ans**, coordinatrice salariée de l'association.
- **À la radio depuis quinze ans.**
- **Son travail** : l'équipe, le bureau, les subventions, les partenaires, les obligations de la radio.
- **Son matériel** : un ordinateur portable, son téléphone, et beaucoup de réunions.
- **À l'aise** avec les gens, les budgets, les tableurs et les formulaires en ligne. **Pas à l'aise** avec tout ce qui ressemble à un terminal.
- **Son temps** : un temps plein, dont une petite part dans la console.

Hélène accueille une dizaine de bénévoles à chaque rentrée, et en voit partir autant. C'est à elle qu'on demande « tu peux me redonner mon mot de passe ? ». Elle n'est pas technicienne. Elle est admin parce que quelqu'un doit l'être, au local, en journée.

## Ce qu'elle veut

- Donner à chacun le bon accès, vite, et le retirer quand il part.
- Que l'identité de la station soit juste partout : nom, accroche, adresse du flux.
- Savoir que l'antenne va bien, sans lire de journal technique.
- Tenir les obligations de la radio : relevés de diffusion, données personnelles, licence du logiciel.
- Ne pas dépendre de Karim pour une décision qui n'est pas technique.

## Ce qui la freine

- Les comptes créés un par un, et les mots de passe à transmettre.
- Ne pas savoir qui a changé quoi, quand la grille a bougé.
- Le diagnostic de l'automate, écrit pour un technicien.
- Les réglages qui demandent encore une commande sur la machine.

## Son parcours

1. **Un nouveau bénévole.** **Réglages → Comptes**, **Nouveau compte** : un identifiant, un mot de passe, un rôle (Animateur, Programmateur ou Admin), et **Peut passer en direct** s'il a une émission en direct. Elle choisit ensuite ce compte dans son émission, en **Compte du plateau** (**Programmation → Semaine**) : le champ ne liste les comptes que pour un admin.
2. **Sa fiche.** Elle y voit les créneaux qui le nomment. Elle crée son jeton d'encodeur s'il n'y arrive pas seul, et règle le mot de passe du dossier de la station pour une programmatrice.
3. **Un départ.** Elle supprime le compte, après confirmation.
4. **La station.** **Réglages → Station** : le nom, le nom court, l'accroche, la langue, les adresses publiques du flux et de `now.json`. Un enregistrement change tout de suite le nom affiché.
5. **Un souci dans l'Agenda.** Elle peut couper l'agenda, depuis son menu ⋯ : la grille joue seule, et rien n'est effacé.
6. **Une alerte.** Le lien **Diagnostic** du bandeau ouvre **Réglages → Automate** : santé, dépannage, statut. Elle en lit le résumé, et passe le reste à Karim.

## Le moment qui compte

Un samedi de septembre, dix nouveaux bénévoles arrivent. Hélène crée dix comptes, choisit un rôle pour chacun, allume **Peut passer en direct** pour trois d'entre eux, puis transmet dix mots de passe, un par un.

Deux bénévoles de l'an dernier sont partis. Avant de supprimer leurs comptes, elle ouvre leurs fiches : tant qu'une émission nomme un compte, personne d'autre que lui, ou un admin, ne peut y passer en direct.

## Ce que BUTTON fait déjà pour elle

- Trois rôles et un interrupteur, jamais les six droits du moteur : [api.md](../api.md#rôles-et-droits).
- Les réglages de la station se changent dans la console, sans reconstruire d'image.
- Couper l'agenda n'efface rien.
- Un admin crée ou renouvelle le jeton d'encodeur d'un autre compte.
- Le lien « Code source », étiqueté AGPL, reste dans le menu de chaque compte.

## Ce qui coince encore

- **Qui a changé quoi ?** Un journal des actions de l'équipe, lisible dans Réglages : SEC-10, en [P2](../feuille-de-route/P2.md).
- **Inviter par un lien** plutôt que transmettre un mot de passe, et des rôles plus fins : FON-07, en [P3](../feuille-de-route/P3.md).
- **La double authentification** des admins : SEC-08, en P2. Un mot de passe d'admin volé donne toute l'antenne.
- **Les relevés SACEM et SPRE** : FON-01, en P2. **Les statistiques d'écoute**, pour les bilans et les demandes de subvention : FON-03, en P3.
- **Les données personnelles** : la durée de conservation des journaux d'Icecast, l'effacement d'un compte : FON-11, en P3.
- **Le code source de la version en service**, que l'AGPL doit à chaque utilisateur, animateurs compris : le lien doit y mener, LEG-02, en [P1](../feuille-de-route/P1-mise-en-prod.md).
- **Refuser le mot de passe du compte au direct** demande encore une commande sur la machine : [passer-en-direct.md](../exploitation/passer-en-direct.md#refuser-le-mot-de-passe-du-compte).
- **Le logo de la station** ne s'envoie pas encore depuis la console : GEN-04. **Les mises à jour** ne s'y voient pas encore : MAJ-07. Les deux en P2.

## Concevoir pour elle

- Un geste d'admin dit sa conséquence avant d'agir : supprimer un compte, renouveler un jeton, couper l'agenda.
- Le diagnostic commence par une phrase qu'elle peut lire, et transmettre.
- Une décision de la radio ne demande jamais un terminal.
- Créer dix comptes ne prend pas dix fois le temps d'un seul.
