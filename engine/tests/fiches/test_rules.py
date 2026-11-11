"""Les règles des fiches : les cas de `tests/radio-catalogue.test.ts`, dans Hopper.

Ses blocs « durée du fichier », « graphies », « année », « genre musical » et « femme
ou minorité de genre ». Une attente sur plusieurs champs se lit comme un
`toMatchObject` : seuls les champs nommés comptent.
"""

import re

import pytest

from radiotomate.fiches.rules import (
    FAMILIES,
    ArtistFacts,
    Member,
    Members,
    Period,
    Person,
    YearInput,
    calmed,
    clean_isrc,
    duration_level,
    exotic_letters,
    fmg_verdict,
    genre_family,
    isrc_year,
    placeholder_album,
    propose_year,
    respell_artists,
    respelling,
    retyped,
    same_artist_name,
    split_tail,
    without_edition_mentions,
    without_foreign_mentions,
)


def fields(value, expected: dict) -> dict:
    """Les champs de `value` que `expected` nomme."""
    return {key: getattr(value, key) for key in expected}


# ===== Durée du fichier =====


@pytest.mark.parametrize(
    ("radio", "found", "expected"),
    [
        (188, 189, {"level": "sûr", "gap": 1, "why": None}),
        (345, 355, {"level": "sûr"}),
        # Le fichier de 84 s face à « Glimity Glamity » (5:41), et 46 s d'écart pour
        # Vladimir and his Orchestra.
        (
            84,
            341,
            {"level": "à revoir", "gap": 257, "why": "durée : 1:24 ici, 5:41 trouvé"},
        ),
        (184, 138, {"level": "à revoir"}),
        (200, None, {"level": "à revoir", "why": "durée du morceau trouvé inconnue"}),
        # NaN, comme pour JavaScript, est une durée inconnue.
        (
            float("nan"),
            200,
            {"level": "à revoir", "why": "durée du morceau trouvé inconnue"},
        ),
    ],
)
def test_duration_confirms_within_ten_seconds(radio, found, expected):
    """La durée confirme à 10 s près, et signale le reste."""
    assert fields(duration_level(radio, found), expected) == expected


# ===== Graphies =====


@pytest.mark.parametrize(
    ("title", "without"),
    [
        ("El Nuevo Barretto (Remastered 2024)", "El Nuevo Barretto"),
        ("Beverly - Original", "Beverly"),
        ("Kallio (Original Mix)", "Kallio"),
        ("Acid (Remastered 2024)", "Acid"),
        ("Toundsrack (feat. tajima hal)", "Toundsrack (feat. tajima hal)"),
        ("Walk Tall (Live)", "Walk Tall (Live)"),
        ("Strings Of Life (Dub)", "Strings Of Life (Dub)"),
    ],
)
def test_without_edition_mentions(title, without):
    """Les mentions d'édition partent, pas les versions ni les invités."""
    assert without_edition_mentions(title) == without


@pytest.mark.parametrize(
    ("radio", "found", "proposed"),
    [
        ("GLIMITY_GLAMITY", "Glimity Glamity", "Glimity Glamity"),
        ("Celestial_blues", "Celestial Blues", "Celestial Blues"),
        (
            "On ne se voit pas tres souvent",
            "On ne se voit pas très souvent",
            "On ne se voit pas très souvent",
        ),
        ("I m gonna let him ride", "I'm Gonna Let Him Ride", "I'm Gonna Let Him Ride"),
        ("Yeuze Low ", "Yeuze Low", "Yeuze Low"),
        ("Wanna Do My Thing", "Wanna Do My Thing", None),
        # Une casse déjà soignée reste : seule la casse change, et ni tout en
        # majuscules ni tout en minuscules.
        ("He's a Superstar", "He's A Superstar", None),
        ("Bass Drum Of Death", "Bass Drum of Death", None),
        ("Balanço De Açaí", "Balanço de Açaí", None),
        # Une mention du fichier (« (1970) ») n'est pas une graphie : rien.
        ("Allegretto Per Signora (1970)", "Allegretto per signora", None),
    ],
)
def test_respelling_proposes_only_the_spelling(radio, found, proposed):
    """Seulement la graphie : casse, soulignés, accents."""
    assert respelling(radio, found) == proposed


@pytest.mark.parametrize(
    ("radio", "found", "proposed"),
    [
        ("l'éclair", "L'Eclair", "L'Éclair"),
        ("Les Frères Smith", "Les Freres Smith", None),
        ("Cathédrale", "Cathedrale", None),
        ("Musa Da Babilônia", "Musa da Babilonia", None),
        ("CŒUR", "Coeur", None),
        ("BJØRN TORSKE", "Bjorn Torske", None),
        # Le « İ » turc en capitale : la minuscule a déjà son point.
        ("YENİ YÜREKLE", "Yeni Yürekle", "Yeni Yürekle"),
        # Une casse soignée reste ; les accents et la ponctuation trouvés s'y ajoutent.
        ("Funk Dos Bromanticos", "Funk Dos Bromânticos", "Funk Dos Bromânticos"),
        ("Guess Whos Back", "Guess Who's back", "Guess Who's Back"),
        ("Train Fantôme ", "TRAIN FANTOME", "Train Fantôme"),
        ("Riot Patanegra", "Riot Pata Negra", "Riot Pata Negra"),
        (
            "Sly5thave & The Clubcasa Orchestra ",
            "Sly5thAve & The ClubCasa Orchestra",
            "Sly5thAve & The ClubCasa Orchestra",
        ),
        (
            "Tamrat Ferendji & Sensation Band ",
            "Tamrat FerenDJi & Sensation Band",
            "Tamrat FerenDJi & Sensation Band",
        ),
        ("I'm OK", "I'm Ok", None),
        ("Chagrin D'Amour", "Chagrin d'Amour", None),
        ("DNAE Beats", "DNAEBEATS", "DNAEBEATS"),
        ("Julien RIBOT", "Julien Ribot", None),
        # Un texte surtout en capitales, ou qui commence en minuscule, n'est pas une
        # casse soignée.
        ("ANNEES SOLAIRES Part I", "Années Solaires Part I", "Années Solaires Part I"),
        ("charlie O", "Charlie O.", "Charlie O."),
        ("S job movement", "SJOB Movement", "SJOB Movement"),
        # Une graphie trouvée tout en capitales ne remplace pas une casse.
        ("ed warner", "ED WARNER", None),
    ],
)
def test_respelling_never_drops_an_accent(radio, found, proposed):
    """Jamais un accent ni une lettre particulière retirés."""
    assert respelling(radio, found) == proposed


@pytest.mark.parametrize(
    ("radio", "found", "sentence", "proposed"),
    [
        # MusicBrainz écrit « Q-Tip » avec un trait d'union U+2010 : un tag le
        # chercherait en vain.
        ("Q-Tip", "Q\u2010Tip", False, None),
        (
            "Comin' On Strong (Jamie 3:26 Edit)",
            "Comin\u2019 on Strong (Jamie 3:26 edit)",
            True,
            None,
        ),
        (
            "everything's tuesday",
            "Everything\u2019s Tuesday",
            True,
            "Everything's Tuesday",
        ),
        (
            "Cedric Im Brooks",
            "Cedric \u201cIm\u201d Brooks",
            False,
            'Cedric "Im" Brooks',
        ),
        # Les parenthèses du fichier ne deviennent pas un tiret.
        (
            "Moribiyassa (Daniel Haaksman Edit)",
            "Moribiyassa - Daniel Haaksman Edit",
            True,
            None,
        ),
    ],
)
def test_respelling_keeps_keyboard_punctuation(radio, found, sentence, proposed):
    """La ponctuation typographique revient à celle du clavier."""
    assert respelling(radio, found, sentence=sentence) == proposed


@pytest.mark.parametrize(
    ("radio", "found", "sentence", "proposed"),
    [
        ("Je ne bois pas beaucoup", "Je Ne Bois Pas Beaucoup", True, None),
        ("Le bourreau et la victime", "Le Bourreau Et La Victime", True, None),
        (
            "Nao buzine que eu estou",
            "Não Buzine Que Eu Estou",
            True,
            "Não buzine que eu estou",
        ),
        (
            "I m gonna let him ride",
            "I'm Gonna Let Him Ride",
            True,
            "I'm gonna let him ride",
        ),
        ("Love don t live here", "Love Don't Live Here", True, "Love don't live here"),
        ("cache cache", "Cache cache", True, "Cache cache"),
        ("THIS TIME", "This Time", True, "This Time"),
        # Un nom d'artiste n'est pas une phrase.
        (
            "Vladimir and his orchestra",
            "Vladimir And His Orchestra",
            False,
            "Vladimir And His Orchestra",
        ),
    ],
)
def test_respelling_leaves_a_sentence(radio, found, sentence, proposed):
    """Un titre ou un album écrit comme une phrase reste tel quel."""
    assert respelling(radio, found, sentence=sentence) == proposed


@pytest.mark.parametrize(
    ("radio", "found", "sentence", "fixed"),
    [
        ("Peaches in regalia", "Peaches En Regalia", True, "Peaches en regalia"),
        (
            "All Through The Night Buttobas",
            "ALL THROUGH THE NIGHT BUTTOBASE!!",
            True,
            "All Through The Night Buttobase!!",
        ),
        (
            "Meryem / Say The Truth",
            "Say the Truth and Run",
            True,
            "Say The Truth And Run",
        ),
        (
            "Forever Comes to and End",
            "Forever Comes to an End",
            True,
            "Forever Comes to an End",
        ),
        ("Henri Mancini - Birdie Num-num", "Birdie Num-Num", True, "Birdie Num-num"),
        (
            "Beatrice - gyere kislány,gyere",
            "Gyere kislány, gyere",
            True,
            "Gyere kislány, gyere",
        ),
        ("Café de la danse", "Cafe De La Dance", True, "Café de la dance"),
        # Un mot coupé autrement, la suite d'un mot : la graphie trouvée, sans
        # capitales criées.
        ("F - - - It All", "F**k It All", True, "F**k It All"),
        ("Hook N Sling", "HOOK 'N' SLING", True, "Hook 'n' Sling"),
        ("who's hot", "WHO'S HOT", False, "Who's Hot"),
        # Les capitales d'une phrase trouvée sont des noms : « Brasil » reste.
        (
            "Pigmalião - Saudac'ao a",
            "Pigmalião - Saudação às aves do Brasil",
            True,
            "Pigmalião - Saudação às aves do Brasil",
        ),
        ("03 Now (Dwson Remix) [m]", "Now(Dwson Remix)", True, "Now (Dwson Remix)"),
        # Sans casse soignée dans le fichier, la graphie trouvée ; en capitales
        # seulement si le fichier l'était.
        ("GWEN MC RAE", "Gwen McCrae", False, "Gwen McCrae"),
        ("Bjorn riis", "Bjørn Riis", False, "Bjørn Riis"),
        ("the spec lady", "THE SPACE LADY", False, "The Space Lady"),
        ("Melissa Lavaux", "Melissa Laveaux", False, "Melissa Laveaux"),
    ],
)
def test_retyped_fixes_a_typo_the_file_s_way(radio, found, sentence, fixed):
    """Une faute corrigée à la manière du fichier."""
    assert retyped(radio, found, sentence=sentence) == fixed


@pytest.mark.parametrize(
    ("found", "radio", "without"),
    [
        (
            "Bara to Yaju (Live at The Mayan Theatre, Los Angeles, July,2019)",
            "Bara To Yajuu",
            "Bara to Yaju",
        ),
        (
            "Land Of 1000 Dances (original unedited version)",
            "LAND_OF_THE_1000 dances",
            "Land Of 1000 Dances",
        ),
        ("Song - Live at Wembley", "Song", "Song"),
        ("Superman feat. Sean P", "SUPERMEN", "Superman"),
        (
            'Theme Du Gorille From "Le Gorille Vous Salue Bien"',
            "Theme du gorille",
            "Theme Du Gorille",
        ),
        # Une mention que le fichier écrit reste, une suite qui n'est pas une version
        # aussi.
        (
            "Let Your Heart Be Free (2007 edit)",
            "LET_YOUR_HEART_BE_FREE_2007_EDIT",
            "Let Your Heart Be Free (2007 edit)",
        ),
        (
            "You Got the Power - To Turn Me On",
            "you got the power",
            "You Got the Power - To Turn Me On",
        ),
        # Ces deux-là sont dans le bloc « troisième passe » de Hopper : des
        # parenthèses dans des parenthèses, une mention écrite gardée.
        (
            "Waitin' For The DJ (Album Version (Explicit))",
            "waitin for the dj ft bilal",
            "Waitin' For The DJ",
        ),
        (
            "Swastika Eyes [Chemical Brothers Mix] (Remastered)",
            "Swasika Eyes [Chemical Brothers Mix]",
            "Swastika Eyes [Chemical Brothers Mix]",
        ),
    ],
)
def test_without_foreign_mentions(found, radio, without):
    """Une correction n'ajoute pas de mention que le fichier n'a pas."""
    assert without_foreign_mentions(found, radio) == without


@pytest.mark.parametrize(
    ("title", "split"),
    [
        ("Murky Racing - Featuring Mocky", ("Murky Racing", "- Featuring Mocky")),
        ("^eker Olan (Kozmonot Rework)", ("^eker Olan", "(Kozmonot Rework)")),
        (
            "You Got the Power - To Turn Me On",
            ("You Got the Power - To Turn Me On", ""),
        ),
        # Les règles de JavaScript, relevées par Node : U+FEFF est une espace, et
        # « FEATURİNG », avec le « İ » turc, n'est pas « featuring ».
        ("Song (Live)\ufeff", ("Song", "(Live)")),
        (
            "BU GECE FEATUR\u0130NG G\u00d6KSEL",
            ("BU GECE FEATUR\u0130NG G\u00d6KSEL", ""),
        ),
    ],
)
def test_split_tail(title, split):
    """La base corrigée, les mentions du fichier gardées : du bloc « troisième
    passe » de Hopper."""
    assert split_tail(title) == split


@pytest.mark.parametrize(
    ("text", "calm"),
    [
        ("FEAT PRINCE RAPID", "Feat Prince Rapid"),
        ("(DON'T STOP)", "(Don't Stop)"),
        ("feat Prince Rapid", "feat Prince Rapid"),
    ],
)
def test_calmed(text, calm):
    """Un texte en capitales, une capitale par mot : d'après l'exemple de Hopper."""
    assert calmed(text) == calm


@pytest.mark.parametrize(
    ("text", "exotic"),
    [("Nehḗz fiúk", True), ("Nehéz fiúk", False), ("Wśród pampasów", False)],
)
def test_exotic_letters(text, exotic):
    """Des lettres au-delà de l'alphabet latin étendu : d'après l'exemple de Hopper."""
    assert exotic_letters(text) is exotic


@pytest.mark.parametrize(
    ("radio", "found", "proposed"),
    [
        ("HUSH_PUPPIES", ["Hushpuppies"], "Hushpuppies"),
        ("CHEB_I_SABBAH", ["Cheb i Sabbah"], "Cheb i Sabbah"),
        (
            "Vladimir and his orchestra",
            ["Vladimir And His Orchestra"],
            "Vladimir And His Orchestra",
        ),
        (
            "kieran hebden & steve reid",
            ["Kieran Hebden", "Steve Reid"],
            "Kieran Hebden & Steve Reid",
        ),
        (
            "MOODOID feat. melody prochet",
            ["Moodoïd", "Melody Prochet"],
            "Moodoïd feat. Melody Prochet",
        ),
        ("Dornik", ["Dornik"], None),
        # Un artiste du fichier que la source ne crédite pas : rien.
        ("DELtatron, Nightfeelings, LAO", ["Deltatron"], None),
        ("Driver&Driver", ["Driver"], None),
    ],
)
def test_respell_artists_keeps_the_file_s_separators(radio, found, proposed):
    assert respell_artists(radio, found) == proposed


@pytest.mark.parametrize(
    ("radio", "name", "same"),
    [
        ("HUSH_PUPPIES", "Hushpuppies", True),
        ("paul revere and the raiders", "Paul Revere and the Raiders", True),
        ("felakuti", "Fela Kuti", True),
        ("Kieran Hebden & Steve Reid", "Kieran Hebden", True),
        # La page Deezer « Driver » réunit des homonymes : ce n'est pas le duo
        # « Driver&Driver ».
        ("Driver&Driver", "Driver", False),
        ("Brownswood", "FaltyDL", False),
        ("Nomak", None, False),
    ],
)
def test_same_artist_name(radio, name, same):
    """Un artiste rejoint par identifiant porte-t-il le nom du fichier ?"""
    assert same_artist_name(radio, name) is same


@pytest.mark.parametrize(
    ("album", "placeholder"),
    [
        ("title", True),
        ("No Title", True),
        ("", True),
        ("  ", True),
        ("LALA", False),
        ("Objects [via XLR8R]", False),
        ("25 ans de Radio Nova (Boxset)", False),
        # Des marqueurs de langue, semble-t-il : jamais remplacés.
        ("|Anglais", False),
        ("|Français", False),
        ("|Aucune", False),
        ("|INCONNUE", False),
    ],
)
def test_placeholder_album(album, placeholder):
    assert placeholder_album(album) is placeholder


@pytest.mark.parametrize(
    ("text", "isrc"),
    [("US-RC1-76-07839", "USRC17607839"), ("voiceinside.", None), ("", None)],
)
def test_clean_isrc(text, isrc):
    assert clean_isrc(text) == isrc


# ===== Année =====


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        # L'année du fichier n'est jamais remplacée.
        (
            YearInput(radio="1971", edition="1999-01-01", recording="1971"),
            {"year": None, "source": None, "review": None},
        ),
        # La plus ancienne date connue, MusicBrainz à égalité. Andy Bey, « Celestial
        # Blues » : Deezer donne la réédition de 2003, MusicBrainz la sortie de 1974.
        (
            YearInput(
                radio="",
                edition="2003-05-26",
                edition_source="Deezer",
                recording="1974",
            ),
            {"year": "1974", "source": "MusicBrainz (première sortie)", "review": None},
        ),
        # War, « The Cisco Kid » : l'ISRC est inconnu de MusicBrainz, l'album y est.
        (YearInput(radio="", edition="2015-07-31", album="1972-11"), {"year": "1972"}),
        (
            YearInput(radio="", edition="2015-04-06", recording="2015-04-04"),
            {"source": "MusicBrainz (première sortie)"},
        ),
        # Une date d'édition seule reste à revoir.
        (
            YearInput(
                radio="",
                edition="2026-10-16",
                edition_source="Deezer",
                album_title="Le foto proibite di una signora per bene",
            ),
            {
                "year": "2026",
                "source": "Deezer (date de l'édition trouvée)",
                "review": "année de l'édition trouvée, peut-être une réédition",
            },
        ),
        (
            YearInput(
                radio="",
                edition="2006-06-12",
                album_title="Eldridge Holmes Selected Hits",
            ),
            {"review": "année d'une compilation ou d'une réédition"},
        ),
        (
            YearInput(radio="", edition="2021-06-25", compilation=True),
            {"review": "année d'une compilation ou d'une réédition"},
        ),
        (
            YearInput(radio="", edition="0000-00-00"),
            {"year": None, "source": None, "review": None},
        ),
        # Galaxy, « Disco Funk » : MusicBrainz ne connaît que la compilation de 2020.
        (
            YearInput(
                radio="",
                edition="2020-02-14",
                recording="2020-02-14",
                album_title="Disques Debs International Vol. 2",
            ),
            {"review": "année d'une compilation ou d'une réédition"},
        ),
        # Paul Revere & the Raiders, « Kicks » : 1966, pas la réédition de 1999.
        (
            YearInput(
                radio="", edition="1999-02-16", recording="1999", isrc="USSM16601060"
            ),
            {
                "year": "1966",
                "source": "ISRC (année d'origine du code)",
                "review": None,
            },
        ),
        # Un code récent ne date pas le morceau : il confirme une sortie de l'année du
        # code ou de la suivante (Animali, 2020).
        (
            YearInput(
                radio="",
                edition="2020-03-06",
                edition_source="Deezer",
                isrc="FR9W11926358",
            ),
            {
                "year": "2020",
                "source": "Deezer (date de l'édition trouvée), confirmée par l'ISRC",
                "review": None,
            },
        ),
        # Lloyd Parks : un code de 2012, une édition de 2017 : rien ne confirme.
        (
            YearInput(radio="", edition="2017-06-02", isrc="USCNC1200086"),
            {
                "year": "2017",
                "review": "année de l'édition trouvée, peut-être une réédition",
            },
        ),
        # Une compilation reste à revoir, même confirmée par son ISRC (Strut, 2020).
        (
            YearInput(
                radio="", edition="2020-02-14", isrc="DEG931911678", compilation=True
            ),
            {"review": "année d'une compilation ou d'une réédition"},
        ),
    ],
)
def test_propose_year(facts, expected):
    assert fields(propose_year(facts), expected) == expected


def test_propose_year_older_than_musicbrainz():
    """Plus ancienne que la fiche MusicBrainz, un remaster rangé à part : la date
    d'édition gagne, à revoir."""
    proposal = propose_year(YearInput(radio="", edition="2018-11-09", recording="2021"))
    assert proposal.year == "2018"
    assert isinstance(proposal.review, str)


@pytest.mark.parametrize(
    ("isrc", "year"),
    [
        ("USSM16601060", "1966"),
        ("USRHD0703008", "2007"),
        ("FR9W11926358", "2019"),
        ("BR-EMI-72-00607", "1972"),
        ("voiceinside.", None),
    ],
)
def test_isrc_year(isrc, year):
    """L'année d'un ISRC, d'origine avant 1986."""
    assert isrc_year(isrc) == year


# ===== Genre musical =====

# Hopper donne aussi le code de genre d'une radio. Les codes d'une station n'entrent
# pas dans BUTTON : un cas qui vérifiait le code vérifie la famille de ce code, la
# seule qui le portait (HIPHOP : hip-hop, REGGAE : reggae-dub, JAZZ : jazz, GROOVE :
# soul-funk, WORLD : monde, ELECTRO : electro).


@pytest.mark.parametrize(
    ("genres", "family"),
    [
        (["Rap/Hip Hop"], "hip-hop"),
        (["Reggae", "Dub"], "reggae-dub"),
        (["R&B", "Soul & Funk"], "soul-funk"),
        (["Musique africaine", "Pop", "Soul & Funk"], "monde"),
        (["Latino"], "monde"),
        (["Techno/House", "Dance"], "electro"),
        (["Alternative", "Rock indé", "Electro"], "rock"),
        (["Films/Jeux vidéo", "Musiques de films"], "film"),
        (["Variété Internationale"], "pop"),
        (["Chanson française"], "chanson"),
        # Apple Music et MusicBrainz, en anglais.
        (["Hip-Hop/Rap"], "hip-hop"),
        (["dubstep"], "electro"),
        (["dub techno"], "electro"),
        (["jazz-funk"], "jazz"),
        (["Singer/Songwriter"], "pop"),
        ([], None),
    ],
)
def test_genre_family(genres, family):
    """Les genres des plateformes, rangés dans une famille, le genre principal
    d'abord."""
    found = genre_family(genres)
    assert (found.name if found else None) == family


def test_families_have_a_short_name_and_a_plain_one():
    """Le nom court s'écrit dans une requête Beets ; le nom en clair est celui de
    Hopper."""
    assert [(family.name, family.label) for family in FAMILIES] == [
        ("hip-hop", "Hip-hop"),
        ("reggae-dub", "Reggae, dub"),
        ("jazz", "Jazz"),
        ("soul-funk", "Soul, funk"),
        ("monde", "Musiques du monde"),
        ("electro", "Électro"),
        ("chanson", "Chanson"),
        ("rock", "Rock"),
        ("blues", "Blues"),
        ("folk-country", "Folk, country"),
        ("pop", "Pop"),
        ("film", "Musique de film"),
        ("classique", "Classique"),
        ("experimental", "Expérimental"),
    ]
    assert all(re.fullmatch(r"[a-z]+(?:-[a-z]+)?", family.name) for family in FAMILIES)


# ===== Femme ou minorité de genre =====


@pytest.mark.parametrize(
    ("person", "expected"),
    [
        (Person(musicbrainz="F"), {"verdict": "oui", "source": "MusicBrainz"}),
        (Person(wikidata="MG"), {"verdict": "oui", "source": "Wikidata"}),
        (
            Person(musicbrainz="H", wikidata="H"),
            {"verdict": "non", "source": "MusicBrainz et Wikidata"},
        ),
        (Person(musicbrainz="H", wikidata="F"), {"verdict": "à vérifier"}),
        (None, {"verdict": "à vérifier", "source": None}),
    ],
)
def test_a_person_has_a_declared_gender_never_a_guessed_one(person, expected):
    assert fields(fmg_verdict(ArtistFacts(person=person)), expected) == expected


def group(source: str, *genders: str | None) -> ArtistFacts:
    return ArtistFacts(
        members=Members(source, tuple(Member(gender) for gender in genders))
    )


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        # War : 9 hommes sur 10 membres connus de MusicBrainz.
        (
            group("MusicBrainz", "H", "H", None, "H", "H", "H", "H", "H", "H", "H"),
            {"verdict": "non", "source": "MusicBrainz : 9 membres connus sur 10"},
        ),
        (group("MusicBrainz", "F", "F", "H"), {"verdict": "oui"}),
        (group("Wikidata", "F", "H"), {"verdict": "mixte"}),
        (group("MusicBrainz", "F", "MG", "H", "H"), {"verdict": "mixte"}),
        # Deux connus sur quatre : les inconnus pourraient tout changer.
        (
            group("MusicBrainz", "F", "H", None, None),
            {"verdict": "à vérifier", "source": "MusicBrainz : 2 membres connus sur 4"},
        ),
        (group("MusicBrainz", None, None), {"verdict": "à vérifier"}),
    ],
)
def test_a_group_has_the_majority_of_its_known_members(facts, expected):
    """Un groupe : la majorité de ses membres connus, si les inconnus n'y changent
    rien."""
    assert fields(fmg_verdict(facts), expected) == expected


# Les Pixies selon MusicBrainz : la bassiste du début, puis trois autres qui se sont
# succédé, toutes des femmes, face à trois hommes.
PIXIES = (
    Member("F", (Period(1986, 1993), Period(2004, 2013))),
    Member("H", (Period(1986, 1993), Period(2004))),
    Member("H", (Period(1986, 1993), Period(2004))),
    Member("H", (Period(1986, 1993), Period(2004))),
    Member("F", (Period(2013, 2013),)),
    Member("F", (Period(2014, 2024),)),
    Member("F", (Period(2024),)),
)
# Un homme parti en 1975, une femme arrivée en 1976, une autre sans dates : tout
# dépend de l'année.
TURNED = (
    Member("H", (Period(1970, 1975),)),
    Member("F", (Period(1976),)),
    Member("F"),
)


@pytest.mark.parametrize(
    ("members", "year", "expected"),
    [
        (
            PIXIES,
            1989,
            {
                "verdict": "non",
                "source": "MusicBrainz : 4 membres connus sur 4 en 1989",
            },
        ),
        # Sans année sûre, chaque formation dit « non ».
        (
            PIXIES,
            None,
            {"verdict": "non", "source": "MusicBrainz : le même pour chaque formation"},
        ),
        # Sans les dates, tous les membres comptent : c'était un « oui » faux.
        (tuple(Member(member.gender) for member in PIXIES), None, {"verdict": "oui"}),
        (
            TURNED,
            1972,
            {
                "verdict": "mixte",
                "source": "MusicBrainz : 2 membres connus sur 2 en 1972",
            },
        ),
        (TURNED, 1980, {"verdict": "oui"}),
        (
            TURNED,
            None,
            {
                "verdict": "à vérifier",
                "source": (
                    "MusicBrainz : la formation a changé, sans année sûre du disque"
                ),
            },
        ),
        # Une année hors des dates connues : comme sans année.
        (PIXIES, 1960, {"verdict": "non"}),
    ],
)
def test_a_group_is_judged_on_its_lineup_of_the_year(members, year, expected):
    """Un groupe : sa formation de l'année du disque."""
    facts = ArtistFacts(members=Members("MusicBrainz", members, year))
    assert fields(fmg_verdict(facts), expected) == expected
