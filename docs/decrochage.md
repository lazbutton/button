# Décrochage

Le partage avec une autre radio utilise ce qui est déjà dans le moteur. Aucun essai avec Studio Zef, Radio Campus ou P-Node n’a été fait.

## Ils prennent notre flux

Le partenaire pointe son relais vers :

`https://radio.lazbutton.xyz/button.mp3`

C’est du HTTP/1.1. La page `https://flux.gabbler.band/ntf/` joue ce même flux. Il n’y a pas encore de mount séparé pour la NTF.

## On prend leur flux

Dans les carts, un cart en mode relais porte l’URL du partenaire. L’horloge le pousse sur le créneau. Liquidsoap joue dans cet ordre : harbor, relais, carts, jingles, auto-DJ. Un direct local passe donc devant le relais. À la fin de la durée du cart, le relais s’arrête.

L’URL, le mount et le format à donner à Olmo pour un relais 24/7 ne sont pas calés.
