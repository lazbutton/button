## Fiche

L'identifiant de la fiche de la [feuille de route](../docs/feuille-de-route/README.md), comme SEC-01, ou « aucune ».

## Ce qui change

## Pourquoi

## Comment le vérifier

## À cocher

- [ ] `./scripts/verifier.sh` passe.
- [ ] Ce qui change a des tests.
- [ ] Si une route JSON change : la console suit, `docs/api.md` aussi, et la route est dans la liste de nginx.
- [ ] Si le schéma de la base change : une nouvelle migration `vNN.py`, avec `downgrade` et son test.
- [ ] Une ligne dans `CHANGELOG.md`, sous « Non publié ».
- [ ] Aucune donnée de station : ni secret, ni adresse, ni compte réel.
- [ ] Le texte d'interface ajouté est en français, et l'écran marche en clair, en sombre, au clavier et sur téléphone.
