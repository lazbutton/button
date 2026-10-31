# 0015 · Le flux passe par Caddy, sur le domaine de la console

Acceptée, octobre 2026.

## Contexte

Sur Internet, la console et le flux passent en HTTPS (fiche INS-01). Deux voies : Icecast derrière Caddy, sur le domaine de la console, ou Icecast sur son propre port, avec son propre certificat. Une sonde a d'abord répondu à trois questions. Elle a tourné sur Docker, avec l'Icecast du dépôt (2.4.4, de Debian), une source Liquidsoap 2.4.5 en MP3 à 128 kbit/s, comme le playout, et Caddy 2.11.7. Chaque écoute à travers Caddy était comparée à une écoute directe, lancée au même moment.

- **Le flux passe-t-il sans mise en mémoire tampon ?** Oui. Les octets arrivent au même rythme qu'en direct : un envoi toutes les 118 ms, 137 ms au plus entre deux, 16 ko/s. Caddy renvoie chaque écriture d'Icecast tout de suite, par morceaux de 1,4 ko. C'est vrai avec `flush_interval -1`, et aussi sans : Caddy vide déjà son tampon quand une réponse n'annonce pas sa longueur, comme un flux. Recharger la configuration de Caddy ne coupe pas l'écoute. Un auditeur qui part quitte Icecast en 0,2 s.
- **Les métadonnées ICY passent-elles ?** Oui, en HTTP/1.1 comme en HTTP/2 : l'en-tête `icy-metaint`, puis les titres dans le flux, aux mêmes endroits qu'en direct.
- **Icecast voit-il l'adresse des auditeurs ?** Non. Il voit celle de Caddy pour chaque écoute. Icecast 2.4.4 ne lit pas `X-Forwarded-For`, même avec une balise `<x-forwarded-for>` : son binaire n'en connaît pas le nom. Caddy, lui, voit l'adresse du client, et remplace l'en-tête qu'un client envoie lui-même.

## Décision

- Icecast est derrière Caddy, sur le domaine de la console. Caddy lui relaie les mounts à la racine, comme `/button.mp3`, et `status-json.xsl`, en lecture seulement. L'administration d'Icecast et l'entrée des sources ne passent pas par Caddy, ni le mount WAV du moniteur.
- Personne ne garde l'adresse des auditeurs : Icecast ne la voit pas, Caddy n'a pas de journal des accès, et il la retire de ses messages. Sans ce filtre, Caddy note le départ de chaque auditeur, avec son adresse.

## Conséquences

- Un seul certificat, que Caddy renouvelle sans couper le flux. Icecast n'a ni certificat ni port public. Le flux est sur le port 443, ouvert sur les réseaux d'entreprise ou d'école, qui ferment souvent les autres ports.
- La CSP de la console n'a rien à déclarer : le flux, son statut et `now.json` sont sur son origine.
- Icecast compte toujours les auditeurs et leur pic. Les statistiques par adresse disparaissent : auditeurs uniques, pays. Une station qui en a besoin les tirera d'un journal des accès de Caddy, qui contiendra alors des données personnelles : durée de conservation, information des auditeurs.
- Une règle d'Icecast par adresse, comme un bannissement, viserait Caddy, donc tous les auditeurs. Il n'y en a pas aujourd'hui.
- L'autre voie reste ouverte : l'Icecast de Debian est construit avec OpenSSL. Elle demanderait de copier le certificat de Caddy à chaque renouvellement, puis de redémarrer Icecast, ce qui coupe l'écoute.
- La fiche INS-01 suit cette décision.
