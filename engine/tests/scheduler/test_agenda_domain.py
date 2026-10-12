"""Pure rules of the Agenda: Paris walls, the hour changes, repeats, states."""

from datetime import date, datetime, timedelta, timezone

import pytest

from radiotomate.domain.agenda import (
    AIR_UPCOMING,
    KIND_LIVE,
    KIND_SET,
    ORIGIN_BANK,
    ORIGIN_DEPOT,
    PREP_ANALYSING,
    PREP_READY,
    PREP_REVIEW,
    PREP_WAITING,
    FileFacts,
    TodoInput,
    deposit_open,
    iso_paris,
    loudness_gain,
    nth_of_month,
    occurrence_walls,
    parse_instant,
    playable,
    prep_state,
    repeat_days,
    slug,
    todo_lines,
    validate_window,
    wall_to_utc,
)
from radiotomate.domain.errors import DomainValidationError

UTC = timezone.utc


def test_wall_to_utc_follows_summer_and_winter_time():
    assert wall_to_utc(datetime(2026, 10, 24, 22, 0)) == datetime(
        2026, 10, 24, 20, 0, tzinfo=UTC
    )
    assert wall_to_utc(datetime(2026, 12, 24, 22, 0)) == datetime(
        2026, 12, 24, 21, 0, tzinfo=UTC
    )


def test_night_of_the_october_change_lasts_one_hour_more():
    start = wall_to_utc(datetime(2026, 10, 25, 1, 0))
    end = wall_to_utc(datetime(2026, 10, 25, 4, 0))
    assert end - start == timedelta(hours=4)
    # 02:30 happens twice: the first one, summer time.
    assert iso_paris(wall_to_utc(datetime(2026, 10, 25, 2, 30))).endswith("+02:00")


def test_the_hour_skipped_in_march_is_refused():
    with pytest.raises(DomainValidationError) as caught:
        wall_to_utc(datetime(2027, 3, 28, 2, 30))
    assert "n'existe pas" in caught.value.message


def test_parse_instant_reads_walls_and_offsets():
    assert parse_instant("2026-11-07T22:00", field="start") == datetime(
        2026, 11, 7, 21, 0, tzinfo=UTC
    )
    assert parse_instant("2026-11-07T22:00:41+01:00", field="start") == datetime(
        2026, 11, 7, 21, 0, tzinfo=UTC
    )
    with pytest.raises(DomainValidationError):
        parse_instant("", field="start")
    with pytest.raises(DomainValidationError):
        parse_instant("samedi soir", field="start")


def test_validate_window():
    start = datetime(2026, 11, 7, 21, 0, tzinfo=UTC)
    validate_window(start, start + timedelta(hours=2))
    with pytest.raises(DomainValidationError):
        validate_window(start, start)
    with pytest.raises(DomainValidationError):
        validate_window(start, start + timedelta(hours=25))


def test_repeat_weekly_and_every_two_weeks():
    first = date(2026, 11, 6)
    assert repeat_days(first, "weekly", count=3) == [
        date(2026, 11, 6),
        date(2026, 11, 13),
        date(2026, 11, 20),
    ]
    assert repeat_days(first, "biweekly", until=date(2026, 12, 4)) == [
        date(2026, 11, 6),
        date(2026, 11, 20),
        date(2026, 12, 4),
    ]


def test_repeat_monthly_keeps_the_rank_of_the_weekday():
    # 6 November 2026 is the first Friday of the month.
    assert nth_of_month(date(2026, 11, 6)) == 1
    days = repeat_days(date(2026, 11, 6), "monthly", count=4)
    assert days == [
        date(2026, 11, 6),
        date(2026, 12, 4),
        date(2027, 1, 1),
        date(2027, 2, 5),
    ]
    # 27 November 2026 is the last Friday.
    assert nth_of_month(date(2026, 11, 27)) == -1
    last = repeat_days(date(2026, 11, 27), "monthly", count=3)
    assert last == [date(2026, 11, 27), date(2026, 12, 25), date(2027, 1, 29)]


def test_repeat_needs_an_end_and_stays_under_52():
    with pytest.raises(DomainValidationError):
        repeat_days(date(2026, 11, 6), "weekly")
    with pytest.raises(DomainValidationError):
        repeat_days(date(2026, 11, 6), "weekly", count=60)
    assert len(repeat_days(date(2026, 1, 2), "weekly", until=date(2030, 1, 1))) == 52


def test_a_series_keeps_its_paris_hour_across_the_change():
    walls = occurrence_walls(
        datetime(2026, 10, 23, 22, 0),
        datetime(2026, 10, 24, 0, 0),
        [date(2026, 10, 23), date(2026, 10, 30)],
    )
    starts = [wall_to_utc(start) for start, _ in walls]
    assert iso_paris(starts[0]) == "2026-10-23T22:00+02:00"
    assert iso_paris(starts[1]) == "2026-10-30T22:00+01:00"


def test_prep_state_and_playable():
    ok_bank = FileFacts(origin=ORIGIN_BANK, duration=3600, status="ok")
    ok_depot = FileFacts(origin=ORIGIN_DEPOT, duration=3600, status="ok")
    pending = FileFacts(origin=ORIGIN_DEPOT, duration=0, status="pending")
    broken = FileFacts(
        origin=ORIGIN_DEPOT, duration=0, status="error", error="Fichier illisible"
    )
    assert prep_state(KIND_SET, file=None, rights=False, host_username="") == (
        PREP_WAITING,
        "Set attendu",
    )
    assert prep_state(KIND_SET, file=ok_bank, rights=False, host_username="")[0] == (
        PREP_READY
    )
    assert prep_state(KIND_SET, file=ok_depot, rights=False, host_username="") == (
        PREP_REVIEW,
        "Droits non cochés",
    )
    assert prep_state(KIND_SET, file=pending, rights=True, host_username="")[0] == (
        PREP_ANALYSING
    )
    assert prep_state(KIND_SET, file=broken, rights=True, host_username="") == (
        PREP_REVIEW,
        "Fichier illisible",
    )
    assert prep_state(KIND_LIVE, file=None, rights=False, host_username="dj")[0] == (
        PREP_READY
    )
    assert playable(KIND_SET, file=ok_bank, rights=False)
    assert playable(KIND_SET, file=pending, rights=True)
    assert not playable(KIND_SET, file=ok_depot, rights=False)
    assert not playable(KIND_SET, file=broken, rights=True)
    assert not playable(KIND_LIVE, file=ok_bank, rights=True)


def test_deposit_closes_thirty_minutes_before():
    start = datetime(2026, 11, 7, 21, 0, tzinfo=UTC)
    assert deposit_open(start, start - timedelta(minutes=31))
    assert not deposit_open(start, start - timedelta(minutes=30))


def test_todo_lines():
    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    base = {
        "kind": KIND_SET,
        "title": "Carte blanche",
        "air_status": AIR_UPCOMING,
        "prep_reason": "",
        "guest_name": "DJ Lou",
        "guest_opened": False,
        "has_file": False,
    }
    rows = [
        TodoInput(
            diffusion_id=1,
            start=now + timedelta(hours=30),
            prep=PREP_WAITING,
            **base,
        ),
        TodoInput(
            diffusion_id=2,
            start=now + timedelta(hours=60),
            prep=PREP_WAITING,
            **base,
        ),
        TodoInput(
            diffusion_id=3,
            start=now + timedelta(days=5),
            prep=PREP_WAITING,
            **base,
        ),
        TodoInput(
            diffusion_id=4,
            start=now + timedelta(days=2),
            prep=PREP_WAITING,
            **{**base, "kind": KIND_LIVE, "guest_name": ""},
        ),
        TodoInput(
            diffusion_id=5,
            start=now + timedelta(days=9),
            prep=PREP_WAITING,
            **base,
        ),
    ]
    lines = {line["diffusion_id"]: line["rule"] for line in todo_lines(rows, now)}
    assert lines == {1: "set_waiting", 2: "link_unopened", 4: "live_host"}


def test_loudness_gain_and_slug():
    assert loudness_gain(-14.0) == -4.0
    assert loudness_gain(-60.0) == 24.0
    assert loudness_gain(None) is None
    assert slug("Nuits Tomates : épisode #3") == "nuits-tomates-episode-3"
    assert slug("***") == "agenda"
