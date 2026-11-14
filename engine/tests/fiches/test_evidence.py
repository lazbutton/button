"""Les preuves gardées d'une recherche, et la clé d'un titre (FON-25)."""

import json

from radiotomate.fiches.evidence import from_json, print_key, text_key, to_json
from radiotomate.fiches.fingerprint import Print
from radiotomate.fiches.proposals import (
    DeezerAlbum,
    DeezerDetails,
    Details,
    Match,
    MusicBrainzArtist,
    MusicBrainzDetails,
    MusicBrainzMember,
    SearchResult,
    Track,
    WikidataArtist,
    build_row,
    proposals,
)
from radiotomate.fiches.search import Search


def test_the_key_of_a_title_without_fingerprint():
    track = Track(title="L'Été  indien", artist="Joe Dassin", length=231.6)
    assert text_key(track) == "texte:joe dassin|lete indien|232"
    # La graphie ne change pas la clé ; la durée, si.
    assert text_key(Track(title="l'ete indien", artist="JOE DASSIN", length=232)) == (
        text_key(track)
    )
    assert text_key(Track(title="L'Été indien", artist="Joe Dassin", length=180)) != (
        text_key(track)
    )
    assert text_key(Track(title="x", artist="y")).endswith("|0")


def test_the_key_of_a_fingerprint_is_short_and_stable():
    one = print_key(Print("AQADtEmUaFKSJEmS" * 200, 172.0))
    assert one.startswith("empreinte:")
    assert len(one) == len("empreinte:") + 40
    assert one == print_key(Print("AQADtEmUaFKSJEmS" * 200, 171.0))
    assert one != print_key(Print("AQADautre", 172.0))


def test_the_evidence_goes_to_json_and_back():
    match = Match(
        source="deezer",
        platform="deezer",
        id="1",
        url="https://www.deezer.com/track/1",
        title="Feeling Good",
        artists=("Nina Simone",),
        album="I Put a Spell on You",
        duration_s=172.0,
        why=("titre seul",),
    )
    details = Details(
        deezer=DeezerDetails(
            track_id="1",
            title="Feeling Good",
            duration_s=172.0,
            album=DeezerAlbum(id="9", title="I Put a Spell on You", genres=("Jazz",)),
        ),
        musicbrainz=MusicBrainzDetails(
            artist=MusicBrainzArtist(
                id="mb",
                name="Nina Simone",
                gender="female",
                genres=("jazz",),
                members=(MusicBrainzMember(id="m", name="M", gender="male"),),
            )
        ),
    )
    found = Search(
        SearchResult("trouvé", match, details),
        {"Q1": WikidataArtist(item="Q1", names=("Nina Simone",), genders=("F",))},
    )
    kept = found.evidence()
    data = json.loads(json.dumps(to_json(kept.result, kept.wikidata)))

    result, wikidata = from_json(data)

    assert result == kept.result
    assert wikidata == kept.wikidata
    # Rien sur une personne : ni son genre, ni les membres d'un groupe.
    assert result.details.musicbrainz.artist.gender is None
    assert result.details.musicbrainz.artist.members == ()
    assert wikidata["Q1"].genders == ()
    # Les propositions se refont pareil, sans réseau.
    track = Track(title="feeling good", artist="Nina Simone", length=172)
    assert proposals(build_row(track, result, wikidata)) == proposals(
        build_row(track, kept.result, kept.wikidata)
    )


def test_an_empty_evidence_reads_as_an_error():
    result, wikidata = from_json({})
    assert (result.status, wikidata) == ("erreur", {})
