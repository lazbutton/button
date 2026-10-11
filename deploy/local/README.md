# Banc audio local : Icecast et nowplaying

Pour tester le tuyau audio sans lancer toute la station : un Icecast et le
service « titre en cours », avec des mots de passe de test.

```bash
cd deploy/local
docker compose up --build -d
```

| Service | Adresse |
|---|---|
| Icecast | http://127.0.0.1:18000/ — admin `admin` / `buttonadmin`, source `buttonhackme` |
| Titre en cours | http://127.0.0.1:6820/now.json |
| Hook des métadonnées | `POST /hook`, en-tête `Authorization: Bearer button-dev-secret` |

Icecast écoute sur le port 8000 dans le conteneur, publié en 18000 sur la
machine. Après une modification de `services/icecast/icecast.xml`, reconstruire
l'image (`--build`).

Pour l'interface et la console, voir [`scripts/dev.sh`](../../scripts/dev.sh)
et [`docs/developpement.md`](../../docs/developpement.md). Pour la station
complète, voir [`docs/deploiement.md`](../../docs/deploiement.md).
