# Jean-Pierre · bénévole de permanence

> « Je n'ai pas besoin de tout comprendre. Je veux savoir sur quoi appuyer quand ça ne va pas. »

Persona principal. Dans la console : rôle **Animateur**, sans l'interrupteur du direct.

## Qui il est

- **67 ans**, retraité, ancien agent de la Poste.
- **Bénévole depuis douze ans**, bien avant BUTTON.
- **La permanence du mardi et du jeudi après-midi** au studio : le téléphone, l'accueil des invités, l'antenne.
- **Son matériel** : le PC du studio, un grand écran et une souris. La tablette de la radio quand le PC est pris.
- **À l'aise** avec la radio, les disques et les auditeurs. **Pas à l'aise** avec les mots techniques, les menus cachés et les raccourcis qu'on oublie.
- **Son temps** : huit heures par semaine.

Jean-Pierre connaît les auditeurs fidèles par leur prénom. Il a connu l'ancien automate de la radio, et s'est mis à BUTTON avec méfiance. Il ne parle pas à l'antenne : il la surveille, et passe les dédicaces qu'on lui demande au téléphone.

## Ce qu'il veut

- Que l'antenne ne s'arrête jamais pendant sa permanence.
- Passer une dédicace vite, pendant que l'auditeur est encore en ligne.
- Comprendre ce que dit la pastille quand elle change de couleur.
- Ne rien casser, et pouvoir revenir sur un geste.
- Savoir qui appeler quand il ne peut plus rien faire.

## Ce qui le freine

- Les mots du moteur : playout, battement, Icecast.
- Les gestes qu'on ne peut pas défaire.
- Un message qui dit ce qui se passe, mais pas quoi faire.
- Les petits textes et les petites cibles.
- Un bouton qui change de place après une mise à jour.

## Son parcours

1. Il se connecte au PC du studio et arrive sur **Antenne**. La carte **À l'antenne** donne le titre et le temps restant. Le casque, dans la barre du haut, lui fait entendre le flux public.
2. Une auditrice demande une chanson. Il la cherche dans la **Bibliothèque**, filtre **Musique**, et la met à la suite d'un appui sur Entrée. Dans la **File**, il la remonte, en la glissant ou avec les flèches.
3. Un titre abîmé passe : **Suivant**, ou la barre d'espace.
4. Entre deux titres, il lance un jingle : filtre **Jingles**, puis **Diffuser**.
5. Un auditeur demande quand passe une émission : Jean-Pierre regarde le **Conducteur**. Il le lit sans le changer : c'est le travail de Nadia.

Le pupitre est le même pour tous les rôles. **Programmation** et **Sons** ne sont pas dans sa navigation, et leur adresse affiche « Accès réservé ».

## Le moment qui compte

Mardi, 16 h 12. La pastille passe à **Silence 8 s**, en orange, et un bandeau s'ouvre sur la page Antenne : « Les auditeurs n’entendent plus de son utile. Passe au titre suivant ou lance un son. » Jean-Pierre appuie sur **Suivant**. Le son revient, la pastille aussi.

Un autre jour, le bandeau dit **Automate injoignable** : le pupitre ne reçoit plus de nouvelles depuis 15 h 40. La carte et la file passent en gris. Depuis la console, il ne peut plus rien. Il écoute au casque le flux public, qui joue encore, puis appelle Karim, dont le numéro est scotché sous l'écran.

## Ce que BUTTON fait déjà pour lui

- Chaque panne a son message, en français, sur le pupitre comme dans la barre du haut : [le-flux-est-tombe.md](../exploitation/le-flux-est-tombe.md).
- Un geste resté sans réponse le dit : « L’automate ne répond pas. Le geste a peut-être été fait : vérifie avant de réessayer. » Jean-Pierre ne double pas un geste sans le savoir.
- Un titre retiré de la file se remet avec **Annuler**.
- Le casque se reconnecte seul quand le flux revient.
- Tout le pupitre se fait au clavier. Sur téléphone, les cibles font 40 px au moins.

## Ce qui coince encore

- **Qui prévenir ?** Le bandeau dit depuis quand l'automate se tait, pas à qui le dire. Besoin sans fiche : voir [README.md](README.md#les-besoins-sans-fiche).
- **Les mots du moteur restent dans la pastille** : « Playout injoignable », « Battement perdu ». Le bandeau dit ce qu'ils impliquent ; la pastille garde le mot technique.
- **Une adresse partagée.** Au studio, tous les postes sortent par la même adresse. Cinq mots de passe refusés en 15 minutes y bloquent la connexion 15 minutes, pour tout le monde : [ADR 0013](../decisions/0013-bloquer-l-adresse-jamais-le-compte.md). Les sessions déjà ouvertes continuent.
- **Un mode simple**, qui cache ce dont il n'a pas besoin : UX-07. **Une navigation proche de celle des autres webradios** : UX-01. **Un audit d'accessibilité complet** : UX-08. Tout en [P3](../feuille-de-route/P3.md).

## Concevoir pour lui

- Un message dit ce qui se passe, ce que ça change pour les auditeurs, et quoi faire.
- Pas de mot technique sans sa traduction juste à côté.
- Un geste lourd se confirme, ou se défait.
- La page Antenne garde sa disposition d'une version à l'autre.
- Le bouton qui sauve l'antenne, **Suivant**, reste le plus visible.
