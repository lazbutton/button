"""Les propositions d'un titre, trouvé à la lettre près ou rapproché.

Le cas « assemble MusicBrainz et Wikidata » de `tests/radio-catalogue.test.ts`, dans
Hopper, et pour un titre rapproché, celui de son bloc « troisième passe » qui corrige
à la manière de Rivendell. Hopper ne teste `buildRow` que pour un titre rapproché :
les rangées trouvées à la lettre près sont écrites ici, d'après ses exemples (War,
Andy Bey, Galaxy, les Pixies…). Durées, identifiants et liens y sont des valeurs de
test.
"""

from dataclasses import replace

import pytest

from radiotomate.fiches.proposals import (
    AppleDetails,
    DeezerAlbum,
    DeezerDetails,
    Details,
    Match,
    MusicBrainzArtist,
    MusicBrainzDetails,
    MusicBrainzMember,
    Proposal,
    SearchResult,
    Track,
    WikidataArtist,
    artist_facts,
    build_row,
    fixed_title,
    proposals,
)
from radiotomate.fiches.rules import (
    ArtistFacts,
    Member,
    Members,
    Period,
    Person,
    fmg_verdict,
)
from radiotomate.fiches.variants import (
    Meta,
    RadioTrack,
    radio_variants,
    same_radio_track,
)

# ===== Le verdict, d'après MusicBrainz et Wikidata =====


def mb(kind: str, gender: str | None = None, members=()) -> MusicBrainzArtist:
    return MusicBrainzArtist(
        id="a",
        name="A",
        type=kind,
        gender=gender,
        members=tuple(
            MusicBrainzMember(f"m{at}", f"M{at}", member)
            for at, member in enumerate(members)
        ),
    )


def wd(human: bool, genders=(), members=()) -> WikidataArtist:
    return WikidataArtist(
        item="Q1",
        human=human,
        genders=tuple(genders),
        members={f"Q{at + 10}": tuple(member) for at, member in enumerate(members)},
    )


@pytest.mark.parametrize(
    ("musicbrainz", "wikidata", "year", "facts"),
    [
        (
            mb("Person", "Female"),
            None,
            None,
            ArtistFacts(person=Person(musicbrainz="F")),
        ),
        (
            None,
            wd(True, ["Q6581072", "Q1052281"]),
            None,
            ArtistFacts(person=Person(wikidata="F")),
        ),
        # Deux valeurs de P21 qui ne disent pas la même chose : inconnu.
        (None, wd(True, ["Q6581072", "Q6581097"]), None, ArtistFacts()),
        # Une valeur de P21 inconnue de la table n'est jamais « homme ».
        (None, wd(True, ["Q999"]), None, ArtistFacts()),
        (
            mb("Group", None, ["Male", None]),
            None,
            1972,
            ArtistFacts(
                members=Members("MusicBrainz", (Member("H"), Member()), 1972),
            ),
        ),
        # MusicBrainz ne connaît aucun genre de membre : Wikidata.
        (
            mb("Group", None, [None]),
            wd(False, [], [["Q6581072"], []]),
            None,
            ArtistFacts(members=Members("Wikidata", (Member("F"), Member()))),
        ),
    ],
)
def test_artist_facts_assemble_musicbrainz_and_wikidata(
    musicbrainz, wikidata, year, facts
):
    assert artist_facts(musicbrainz, wikidata, year) == facts


def test_missing_wikidata_members_stay_unknown():
    """Au Pairs : quatre membres chez MusicBrainz, sans genre ; trois chez Wikidata,
    dont deux femmes. Le quatrième manque : deux femmes sur quatre membres ne font
    pas un « oui »."""
    facts = artist_facts(
        mb("Group", None, [None, None, None, None]),
        wd(False, [], [["Q6581072"], ["Q6581072"], []]),
    )
    verdict = fmg_verdict(facts)
    assert (verdict.verdict, verdict.source) == (
        "à vérifier",
        "Wikidata : 2 membres connus sur 4",
    )


# ===== Ce qui n'a rien donné =====


@pytest.mark.parametrize(
    ("result", "level", "reasons"),
    [
        (None, "pas encore cherché", []),
        (SearchResult("écarté"), "écarté", ["sans artiste ou annonce"]),
        (SearchResult("rien"), "introuvable", []),
        (
            SearchResult("erreur", error="Deezer : réponse 503"),
            "erreur",
            ["Deezer : réponse 503"],
        ),
        (SearchResult("erreur"), "erreur", ["erreur"]),
    ],
)
def test_nothing_found_proposes_nothing(result, level, reasons):
    track = Track(title="The Cisco Kid", artist="WAR", length=267)
    row = build_row(track, result, {})
    assert (row.level, row.reasons) == (level, reasons)
    assert proposals(row) == []


# ===== Un titre trouvé à la lettre près =====

# War, « The Cisco Kid » : Deezer, rejoint par l'ISRC, donne la réédition de 2015 ;
# MusicBrainz, la première sortie de l'album, en 1972, et deux membres du groupe.
WAR = Track(title="The Cisco Kid", artist="WAR", length=267)
WAR_MATCH = Match(
    source="deezer",
    platform="deezer",
    id="1",
    url="https://www.deezer.com/track/1",
    title="The Cisco Kid",
    artists=("War",),
    duration_s=267,
    isrc="USRHD0703008",
    artist_id="10129",
)
WAR_ALBUM = DeezerAlbum(
    id="7",
    title="The World is a Ghetto",
    label="Avenue Records",
    date="2015-07-31",
    record_type="album",
    genres=("R&B",),
)
WAR_DEEZER = DeezerDetails(
    track_id="1",
    title="The Cisco Kid",
    duration_s=267,
    isrc="USRHD0703008",
    artist_id="10129",
    artist_name="War",
    album=WAR_ALBUM,
)
WAR_MUSICBRAINZ = MusicBrainzDetails(
    album_date="1972-11",
    artist=MusicBrainzArtist(
        id="war",
        name="War",
        type="Group",
        genres=("funk", "soul"),
        members=(
            MusicBrainzMember("m1", "M1", "Male"),
            MusicBrainzMember("m2", "M2", "Male"),
        ),
    ),
)
WAR_FOUND = SearchResult(
    "trouvé", WAR_MATCH, Details(deezer=WAR_DEEZER, musicbrainz=WAR_MUSICBRAINZ)
)


def test_a_track_found_letter_for_letter():
    row = build_row(WAR, WAR_FOUND, {})
    assert (row.level, row.reasons) == ("sûr", [])
    assert (row.found_at, row.platform, row.url) == (
        "Deezer",
        "Deezer",
        "https://www.deezer.com/track/1",
    )
    assert (
        row.found_title,
        row.found_album,
        row.found_artists,
        row.found_duration,
    ) == (
        "The Cisco Kid",
        "The World is a Ghetto",
        "War",
        267,
    )
    assert proposals(row) == [
        Proposal("artist", "WAR", "War", "sûr", source="Deezer"),
        Proposal("album", "", "The World is a Ghetto", "sûr", source="Deezer"),
        Proposal(
            "year", 0, 1972, "sûr", source="MusicBrainz (première sortie de l'album)"
        ),
        Proposal("label", "", "Avenue Records", "sûr", source="Deezer"),
        Proposal("isrc", "", "USRHD0703008", "sûr", source="Deezer"),
        Proposal("famille", "", "soul-funk", "sûr", source="Deezer : R&B"),
        # Des membres sans dates comptent tout du long : pas de formation de l'année.
        Proposal(
            "fmg", "", "non", "sûr", source="MusicBrainz : 2 membres connus sur 2"
        ),
    ]


def test_values_already_there_are_not_proposed():
    """Une valeur du fichier reste : l'année, le label, un ISRC bien formé, et la
    famille ou le verdict déjà posés."""
    track = Track(
        title="The Cisco Kid",
        artist="War",
        album="The World Is a Ghetto",
        year=1972,
        label="United Artists",
        isrc="USRHD0703009",
        length=267,
        famille="soul-funk",
        fmg="non",
    )
    assert proposals(build_row(track, WAR_FOUND, {})) == []


def test_a_malformed_isrc_is_replaced():
    track = Track(title="The Cisco Kid", artist="War", isrc="voiceinside.", length=267)
    proposed = {
        proposal.key: proposal.value
        for proposal in proposals(build_row(track, WAR_FOUND, {}))
    }
    assert proposed["isrc"] == "USRHD0703008"


@pytest.mark.parametrize(
    ("album", "found", "proposed"),
    [
        ("", "The World is a Ghetto", "The World is a Ghetto"),
        ("title", "The World is a Ghetto", "The World is a Ghetto"),
        (
            "No Title",
            "The World is a Ghetto (Remastered 2015)",
            "The World is a Ghetto",
        ),
        # Un album rempli n'est pas remplacé, seule sa graphie change.
        ("THE_WORLD_IS_A_GHETTO", "The World is a Ghetto", "The World is a Ghetto"),
        ("Greatest Hits", "The World is a Ghetto", None),
        # Des marqueurs de langue, semble-t-il : jamais remplacés.
        ("|Anglais", "The World is a Ghetto", None),
    ],
)
def test_an_album_is_proposed_only_empty_or_placeholder(album, found, proposed):
    album_details = DeezerDetails(
        track_id="1",
        title="The Cisco Kid",
        duration_s=267,
        album=DeezerAlbum(id="7", title=found),
    )
    track = Track(
        title="The Cisco Kid", artist="War", album=album, year=1972, length=267
    )
    result = SearchResult("trouvé", WAR_MATCH, Details(deezer=album_details))
    values = {p.key: p.value for p in proposals(build_row(track, result, {}))}
    assert values.get("album") == proposed


def test_a_duration_apart_puts_every_proposal_under_review():
    """Andy Bey, « Celestial Blues » : la graphie et l'année, mais 46 s d'écart.

    Deezer donne la réédition de 2003, MusicBrainz la sortie de 1974.
    """
    track = Track(title="Celestial_blues", artist="Andy Bey", length=375)
    match = Match(
        "deezer",
        "deezer",
        "2",
        "https://www.deezer.com/track/2",
        "Celestial Blues",
        ("Andy Bey",),
        duration_s=421,
    )
    details = Details(
        deezer=DeezerDetails(
            track_id="2",
            title="Celestial Blues",
            duration_s=421,
            album=DeezerAlbum(
                id="8", title="Experience and Judgment", date="2003-05-26"
            ),
        ),
        musicbrainz=MusicBrainzDetails(recording_date="1974"),
    )
    row = build_row(track, SearchResult("trouvé", match, details), {})
    assert (row.level, row.reasons) == ("à revoir", ["durée : 6:15 ici, 7:01 trouvé"])
    assert row.found_duration == 421
    assert [(p.key, p.value, p.level) for p in proposals(row)] == [
        ("title", "Celestial Blues", "à revoir"),
        ("album", "Experience and Judgment", "à revoir"),
        ("year", 1974, "à revoir"),
    ]


def test_a_doubtful_year_is_under_review_alone():
    """Galaxy, « Disco Funk » : MusicBrainz ne connaît que la compilation de 2020.

    Le titre est sûr, son année est à revoir.
    """
    track = Track(title="Disco Funk", artist="Galaxy", length=300)
    match = Match(
        "deezer",
        "deezer",
        "3",
        "https://www.deezer.com/track/3",
        "Disco Funk",
        ("Galaxy",),
        duration_s=301,
    )
    details = Details(
        deezer=DeezerDetails(
            track_id="3",
            title="Disco Funk",
            duration_s=301,
            album=DeezerAlbum(
                id="9", title="Disques Debs International Vol. 2", date="2020-02-14"
            ),
        ),
        musicbrainz=MusicBrainzDetails(recording_date="2020-02-14"),
    )
    row = build_row(track, SearchResult("trouvé", match, details), {})
    review = "année d'une compilation ou d'une réédition"
    assert (row.level, row.reasons, row.year_review) == ("sûr", [review], review)
    year = next(p for p in proposals(row) if p.key == "year")
    assert year == Proposal(
        "year", 0, 2020, "à revoir", review, "MusicBrainz (première sortie)"
    )


def found(track: Track, meta: Meta) -> SearchResult:
    """La recherche à la lettre près : la variante du fichier qui trouve `meta`."""
    variant = next(
        variant
        for variant in radio_variants(RadioTrack(track.artist, track.title))
        if same_radio_track(variant, meta)
    )
    match = Match(
        source="deezer",
        platform="deezer",
        id="4",
        url="https://www.deezer.com/track/4",
        title=meta.title,
        artists=meta.artists,
        why=variant.why,
        credited=variant.credited,
    )
    return SearchResult("trouvé", match)


@pytest.mark.parametrize(
    ("artist", "title", "artists", "found_title", "proposed"),
    [
        # L'artiste retiré du titre : le titre trouvé est le bon.
        (
            "Coilguns",
            "Coilguns - Carbon Magic",
            ["Coilguns"],
            "Carbon Magic",
            {"title": "Carbon Magic"},
        ),
        # L'artiste lu dans le titre, une émission en guise d'artiste.
        (
            "Combat dub",
            "Zion Train - Logical Progression",
            ["Zion Train"],
            "Logical progression",
            {"title": "Logical progression", "artist": "Zion Train"},
        ),
        # L'artiste et le titre inversés.
        (
            "THE_ANSWER",
            "THE_BLACK_SEEDS",
            ["The Black Seeds"],
            "The Answer",
            {"title": "The Answer", "artist": "The Black Seeds"},
        ),
        # Des soulignés : seulement la graphie.
        (
            "Cheval Fou",
            "L_oreille d_un sourd",
            ["Cheval Fou"],
            "L'oreille d'un sourd",
            {"title": "L'oreille d'un sourd"},
        ),
        # « Porter, Nolan » reste : l'ordre des noms n'est pas une graphie.
        (
            "Porter, Nolan",
            "I Like What You Give",
            ["Nolan Porter"],
            "I Like What You Give",
            {},
        ),
    ],
)
def test_the_title_the_variant_cleaned(artist, title, artists, found_title, proposed):
    """La variante cherchée a nettoyé le texte du fichier : le morceau trouvé a le
    titre à la lettre près, le sien est le bon."""
    track = Track(title=title, artist=artist)
    result = found(track, Meta(title=found_title, artists=tuple(artists)))
    values = {
        p.key: p.value
        for p in proposals(build_row(track, result, {}))
        if p.key in ("title", "artist")
    }
    assert values == proposed


def test_a_nan_duration_is_unknown():
    """NaN, comme pour JavaScript : une durée inconnue, pas une erreur."""
    match = replace(WAR_MATCH, duration_s=float("nan"))
    row = build_row(WAR, SearchResult("trouvé", match), {})
    assert (row.level, row.reasons, row.found_duration) == (
        "à revoir",
        ["durée du morceau trouvé inconnue"],
        None,
    )


@pytest.mark.parametrize(
    ("label", "proposed"),
    [
        # U+FEFF est une espace pour JavaScript : le label est vide.
        ("\ufeff", "Avenue Records"),
        (" ", "Avenue Records"),
        # 0x1F n'en est pas une : le label du fichier reste.
        ("\x1f", None),
    ],
)
def test_an_empty_label_is_read_like_javascript(label, proposed):
    """Les réponses de Hopper, relevées par Node."""
    track = Track(
        title="The Cisco Kid", artist="War", year=1972, label=label, length=267
    )
    values = {p.key: p.value for p in proposals(build_row(track, WAR_FOUND, {}))}
    assert values.get("label") == proposed


def test_tidal_then_deezer_by_isrc():
    match = Match(
        "tidal",
        "deezer",
        "42",
        "https://www.deezer.com/track/42",
        "Swarm Behaviour",
        ("Seleem",),
        duration_s=240,
        isrc="QZ1234567890",
    )
    row = build_row(
        Track(title="Swarm Behaviour", artist="Seleem", length=240),
        SearchResult("trouvé", match),
        {},
    )
    assert (row.found_at, row.platform, row.level) == (
        "Tidal, puis Deezer par l'ISRC",
        "Deezer",
        "sûr",
    )


@pytest.mark.parametrize(
    ("details", "genres", "family"),
    [
        (
            Details(deezer=WAR_DEEZER, apple=AppleDetails(genre="Rock")),
            "Deezer : R&B",
            "soul-funk",
        ),
        (Details(apple=AppleDetails(genre="Rock")), "Apple Music : Rock", "rock"),
        (
            Details(
                musicbrainz=MusicBrainzDetails(
                    artist=MusicBrainzArtist(
                        id="x",
                        name="War",
                        genres=("funk", "soul", "latin", "rock", "jazz"),
                    )
                )
            ),
            "MusicBrainz : funk, soul, latin, rock",
            "soul-funk",
        ),
        (Details(), "", None),
    ],
)
def test_the_family_comes_from_the_main_genre(details, genres, family):
    """Deezer d'abord, sinon Apple Music, sinon les quatre premiers genres de
    MusicBrainz."""
    row = build_row(WAR, SearchResult("trouvé", WAR_MATCH, details), {})
    assert row.genres == genres
    assert (row.family.name if row.family else None) == family


# Les Pixies selon MusicBrainz, comme dans les cas du verdict.
PIXIES = MusicBrainzArtist(
    id="pixies",
    name="Pixies",
    type="Group",
    members=(
        MusicBrainzMember(
            "m1", "M1", "Female", (Period(1986, 1993), Period(2004, 2013))
        ),
        MusicBrainzMember("m2", "M2", "Male", (Period(1986, 1993), Period(2004))),
        MusicBrainzMember("m3", "M3", "Male", (Period(1986, 1993), Period(2004))),
        MusicBrainzMember("m4", "M4", "Male", (Period(1986, 1993), Period(2004))),
        MusicBrainzMember("m5", "M5", "Female", (Period(2013, 2013),)),
        MusicBrainzMember("m6", "M6", "Female", (Period(2014, 2024),)),
        MusicBrainzMember("m7", "M7", "Female", (Period(2024),)),
    ),
)


@pytest.mark.parametrize(
    ("musicbrainz", "source"),
    [
        # La première sortie de l'enregistrement, sûre : la formation de 1989.
        (
            MusicBrainzDetails(recording_date="1989-04-17", artist=PIXIES),
            "MusicBrainz : 4 membres connus sur 4 en 1989",
        ),
        # Seulement une édition que rien ne confirme : chaque formation.
        (
            MusicBrainzDetails(artist=PIXIES),
            "MusicBrainz : le même pour chaque formation",
        ),
    ],
)
def test_a_group_is_judged_on_the_year_when_it_is_sure(musicbrainz, source):
    """Les Pixies, « Debaser » : l'année proposée, si elle est sûre, choisit la
    formation."""
    match = Match(
        "deezer",
        "deezer",
        "5",
        "https://www.deezer.com/track/5",
        "Debaser",
        ("Pixies",),
    )
    deezer = DeezerDetails(
        track_id="5",
        title="Debaser",
        album=DeezerAlbum(id="10", title="Doolittle", date="2004-01-01"),
    )
    details = Details(deezer=deezer, musicbrainz=musicbrainz)
    row = build_row(
        Track(title="Debaser", artist="Pixies"),
        SearchResult("trouvé", match, details),
        {},
    )
    assert (row.verdict, row.verdict_source) == ("non", source)


def test_wikidata_by_the_deezer_page_of_the_same_artist():
    """Une page Deezer rejointe par identifiant, dont un libellé est l'artiste du
    fichier : son genre déclaré."""
    match = Match(
        "deezer",
        "deezer",
        "6",
        "https://www.deezer.com/track/6",
        "Un titre",
        ("Linda Lewis",),
        artist_id="70385",
    )
    wikidata = {
        "70385": WikidataArtist(
            item="Q1",
            names=("Linda Lewis",),
            human=True,
            genders=("Q6581072", "Q1052281"),
        )
    }
    row = build_row(
        Track(title="Un titre", artist="Linda Lewis"),
        SearchResult("trouvé", match),
        wikidata,
    )
    assert (row.verdict, row.verdict_source) == ("oui", "Wikidata")
    assert Proposal("fmg", "", "oui", "à revoir", source="Wikidata") in proposals(row)


def test_the_deezer_page_of_a_namesake_is_refused():
    """La page Deezer « Driver » réunit des homonymes : ce n'est pas le duo
    « Driver&Driver »."""
    match = Match(
        "deezer",
        "deezer",
        "7",
        "https://www.deezer.com/track/7",
        "Un titre",
        ("Driver&Driver",),
        artist_id="42",
    )
    wikidata = {
        "42": WikidataArtist(
            item="Q2", names=("Driver",), human=True, genders=("Q6581097",)
        )
    }
    row = build_row(
        Track(title="Un titre", artist="Driver&Driver"),
        SearchResult("trouvé", match),
        wikidata,
    )
    assert (row.verdict, row.verdict_source) == ("à vérifier", "")
    assert not any(p.key == "fmg" for p in proposals(row))


# ===== Un titre rapproché =====
# Le cas « corrige à la manière de Rivendell ce que la troisième passe a relu », dans
# Hopper : un morceau de Jerzy Milian, rapproché dans l'album du fichier, puis ses
# variantes.

MILIAN = Track(
    title="W[rsd Pampassw",
    artist="Jerzy Milian",
    album="Orkiestra Rozrywkowa PRiTV",
    length=214,
)
MILIAN_MATCH = Match(
    source="rapprochement",
    platform="deezer",
    id="3",
    url="u",
    title="Wśród pampasów",
    artists=("Jerzy Milian",),
    duration_s=213,
    why=(
        "même artiste",
        "titre aux accents perdus",
        "durée à 1 s",
        "dans l'album de la radio",
    ),
)


def close(track: Track, details: Details | None = None, **match):
    """La rangée d'un titre rapproché : le morceau de Jerzy Milian, changé par
    `match`."""
    result = SearchResult("rapproché", replace(MILIAN_MATCH, **match), details)
    return build_row(track, result, {})


def test_a_close_match_repairs_lost_accents():
    row = close(MILIAN)
    assert (row.level, row.title, row.artist) == (
        "rapproché",
        "Wśród pampasów",
        "Jerzy Milian",
    )
    assert row.reasons == [
        "rapproché : même artiste, titre aux accents perdus, durée à 1 s,"
        " dans l'album de la radio"
    ]
    assert proposals(row) == [
        Proposal(
            "title", "W[rsd Pampassw", "Wśród pampasów", "rapproché", source="Deezer"
        )
    ]


def test_a_close_match_keeps_its_own_duration():
    """La durée du morceau rapproché, qui l'a confirmé : Deezer, rejoint par l'ISRC,
    a parfois une autre édition."""
    deezer = DeezerDetails(track_id="3", title="Wśród pampasów", duration_s=300)
    row = close(MILIAN, Details(deezer=deezer))
    assert (row.level, row.found_duration) == ("rapproché", 213)


@pytest.mark.parametrize(
    ("track", "match", "expected"),
    [
        # Une faute corrigée, la mention du fichier gardée.
        (
            replace(MILIAN, artist="Mos Def", title="Auditiorium Ft. Slick Rick"),
            {
                "title": "Auditorium",
                "artists": ("Mos Def feat. Slick Rick",),
                "why": (
                    "artiste crédité autrement",
                    "titre à une faute près",
                    "durée à 0 s",
                    "recherche floue",
                ),
            },
            {"title": "Auditorium Ft. Slick Rick"},
        ),
        # Des accents réparés avec une lettre improbable : le titre reste.
        (
            replace(MILIAN, artist="Neoton Fammlia", title="Nehiz Fizk"),
            {
                "title": "Nehḗz fiúk",
                "artists": ("Neoton Familia",),
                "why": (
                    "artiste à une faute près",
                    "titre aux accents perdus",
                    "durée à 0 s",
                ),
            },
            {"title": "Nehiz Fizk"},
        ),
        # L'artiste et le titre inversés dans le fichier : chacun reprend sa place.
        (
            replace(MILIAN, artist="TI_FI_LA_OU_TE_MADAM", title="ANZALA_DOLOR_VELO"),
            {
                "title": "Ti Fi La Ou Te Madam'",
                "artists": ("Anzala", "Dolor", "velo"),
                "why": ("artiste crédité autrement", "même titre", "durée à 4 s"),
            },
            {"title": "Ti Fi La Ou Te Madam'", "artist": "Anzala, Dolor, velo"},
        ),
        # Une annotation du fichier mise de côté pour chercher : son titre reste.
        (
            replace(MILIAN, title="My Melodi ['We Can Get Down']"),
            {
                "title": "My Melody",
                "why": (
                    "même artiste",
                    "titre à une faute près",
                    "durée à 3 s",
                    "annotation entre crochets retirée",
                ),
            },
            {"title": "My Melodi ['We Can Get Down']"},
        ),
        # Rien d'après SoundCloud, où chaque compte écrit ce qu'il veut.
        (
            MILIAN,
            {"platform": "soundcloud"},
            {"title": "W[rsd Pampassw", "artist": "Jerzy Milian"},
        ),
    ],
)
def test_a_close_match_is_fixed_the_file_s_way(track, match, expected):
    """Corrigé à la manière du fichier, ce que la troisième passe a relu."""
    row = close(track, **match)
    assert {key: getattr(row, key) for key in expected} == expected


# « ğ », abîmé à l'import, devient 0x1F, une espace pour Python, pas pour JavaScript :
# la casse du fichier se lit comme chez Hopper. Ses réponses, relevées par Node. Le
# « i » sans point du turc est à sa place : ruff le signale, à tort ici.
@pytest.mark.parametrize(
    ("radio", "found", "fixed"),
    [
        ("De\x1fmesin Ya\x1fl1 Boya", "Değmesin yağlı boya", "Değmesin Yağlı Boya"),  # noqa: RUF001
        ("Ne O\x1flan Ne K1z", "ne oğlan ne kız", "Ne Oğlan Ne Kız"),  # noqa: RUF001
        ("Da\x1flar Da\x1flar", "Dağlar Dağlar", "Dağlar Dağlar"),
    ],
)
def test_a_title_damaged_by_the_import_keeps_the_file_s_case(radio, found, fixed):
    why = ("même artiste", "titre aux accents perdus", "durée à 1 s")
    row = close(
        replace(MILIAN, title=radio, artist="X"), title=found, artists=("X",), why=why
    )
    assert row.title == fixed


def test_an_artist_damaged_by_the_import_keeps_the_file_s_case():
    why = ("artiste aux accents perdus", "même titre", "durée à 1 s")
    track = replace(MILIAN, title="Song", artist="Selda Ba\x1fcan")
    row = close(track, title="Song", artists=("selda bağcan",), why=why)
    assert row.artist == "Selda Bağcan"


@pytest.mark.parametrize(
    ("radio", "found", "artists", "fixed"),
    [
        # Les notes techniques du fichier partent, ses mentions restent.
        (
            "APKA! forcar o verao (RTM) Master Final (16bit44.1kHz)",
            "Forçar o verão",
            [],
            "Forçar o verão",
        ),
        (
            "Big Mouth AKA The Next Level [Phat Mastered]",
            "03 Big Mouth AKA The Next Level",
            [],
            "Big Mouth AKA The Next Level",
        ),
        (
            "Vancouver and Fairfield remix (2004)",
            "Vancouver and Fairfield (remix)",
            [],
            "Vancouver and Fairfield (remix) (2004)",
        ),
        # Les mêmes mots ne changent rien.
        (
            "Shake Your Body (Down to the Ground)",
            "Shake Your Body Down to the Ground",
            [],
            "Shake Your Body (Down to the Ground)",
        ),
        (
            "Honest Joe's Indian (Early Version)21",
            "Honest Joe's Indian (early version)",
            [],
            "Honest Joe's Indian (Early Version)",
        ),
        (
            "Sleepin Giant ft. Romaine Smith - Hey Girl (Sauce 81 remix)",
            "Hey Girl",
            [],
            "Hey Girl (Sauce 81 remix)",
        ),
        (
            "WORLD IS MINE FEAT PRINCE RAPID",
            "World's Mine",
            [],
            "World's Mine Feat Prince Rapid",
        ),
        # Un numéro de piste et l'artiste dans le titre trouvé, que le fichier n'a pas.
        (
            "Patrona De Los Reclusos (The Latin Brothers)",
            "05 Dj Veekash Patrona De Los Reclusos (The Latin Brothers)",
            ["Dj Veekash"],
            "Patrona De Los Reclusos (The Latin Brothers)",
        ),
    ],
)
def test_fixed_title(radio, found, artists, fixed):
    assert fixed_title(radio, found, artists) == fixed


def test_a_recording_only_on_compilations_has_a_year_to_review():
    """Roy Budd, « Get Carter », 1971 : MusicBrainz ne connaît l'enregistrement que
    par « The Sound Spectrum », une compilation de 1995. Le cas de la recherche dans
    MusicBrainz, dans Hopper, jusqu'à ce qu'il propose."""
    track = Track(title="Get carter", artist="Roy budd", length=198)
    match = Match(
        source="rapprochement",
        platform="musicbrainz",
        id="r2",
        url="https://musicbrainz.org/recording/r2",
        title="Get Carter",
        artists=("Roy Budd",),
        album="The Sound Spectrum",
        duration_s=200.626,
        artist_id="a2",
        why=("même artiste", "même titre", "durée à 3 s"),
        date="1995",
        compilation=True,
    )
    row = build_row(track, SearchResult("rapproché", match), {})
    assert (row.found_at, row.platform) == ("MusicBrainz", "MusicBrainz")
    review = "année d'une compilation ou d'une réédition"
    assert proposals(row) == [
        Proposal("artist", "Roy budd", "Roy Budd", "rapproché", source="MusicBrainz"),
        Proposal("album", "", "The Sound Spectrum", "rapproché", source="MusicBrainz"),
        Proposal(
            "year",
            0,
            1995,
            "à revoir",
            review,
            "MusicBrainz (date de l'édition trouvée)",
        ),
    ]
    # Sans compilation, la date d'un enregistrement rapproché ne propose rien seule.
    alone = build_row(
        track, SearchResult("rapproché", replace(match, compilation=False)), {}
    )
    assert all(proposal.key != "year" for proposal in proposals(alone))
