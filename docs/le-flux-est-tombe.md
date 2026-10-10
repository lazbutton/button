# Le flux est tombé

Vérifier dans cet ordre. Ne pas redémarrer le playout seul : l’interface et le scheduler partagent son réseau.

## 1. Est-ce que le public entend encore quelque chose ?

- Page : `https://flux.gabbler.band/ntf/`
- Flux : `https://radio.lazbutton.xyz/button.mp3`
- Titre : `https://radio.lazbutton.xyz/now.json`

Si la page charge et que `now.json` change de titre, le frontal tient. Le silence est alors dans la banque ou le direct, pas dans Caddy.

## 2. Console

Sur `https://gabbler.band`, l’écran Antenne :

- pastille Silence : plus de son utile à l’antenne ;
- pastille Auditeurs : le frontal répond ;
- pastille Direct : un encodeur est branché, ou non.

Un créneau nommé sans encodeur affiche l’absence au bout d’environ 90 secondes. L’horloge continue à la place.

## 3. Reprendre

Sur Nasgul, recréer ensemble playout, interface et scheduler. Ne pas remplacer le mount public `button.mp3` par un essai.

Sur le VPS-1, les conteneurs du frontal sont dans `/home/debian/icecast`. Recréer Caddy ne relance pas Icecast. Le port 8000 n’accepte la source que depuis Nasgul.

## 4. Revenir en arrière

La copie cohérente de la base se fait avec `scripts/backup-radiotomate.sh` dans le dépôt d’exploitation. Elle reste sur la machine. Une copie hors OVHcloud, et un essai de restauration chronométré, ne sont pas en place. Une sonde Uptime Kuma qui prévient en moins de deux minutes non plus.
