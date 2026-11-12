"""Les fiches de la bibliothèque : reconnaître un titre, proposer de corriger ses tags.

Les règles sont celles de l'outil de catalogue de Hopper, mesurées sur un catalogue
réel, et reprises ici avec leurs cas de test : voir l'ADR 0017. Une fonction garde
le nom de celle de Hopper, en snake_case : une règle corrigée là-bas se retrouve ici.

Les modules des règles ne parlent à aucun service et n'écrivent rien : ni Quart, ni
Beets, ni réseau. Les propositions se refont ainsi sans réseau, d'après ce que les
sources ont déjà dit.

La recherche en ligne a ses propres modules, sans Quart ni Beets : `http`, le client
httpx, avec un seau et un disjoncteur par service ; `sources`, ce que Deezer,
MusicBrainz, Wikidata et AcoustID disent d'un morceau ; `search`, la recherche d'un
titre, de l'empreinte aux détails, et les preuves à garder ; `fingerprint`, l'empreinte
d'un fichier par `fpcalc`.
"""
