"""La page « Mises à jour » de la console (MAJ-07) : GET /system/updates.json,
POST et DELETE /system/updates/request.json, pour un admin.

La console ne pilote jamais Docker : le bouton écrit une demande, dans le dossier
des données, et la commande station de l'hôte la prend
(``radiotomate maintenance updates``). GitHub est joué par un faux transport.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.services import updates
from tests.scheduler.test_admin_json import _admin_client

NOTES_130 = (
    "- La page Mises à jour.\n\n**Mise en service.** Rien à faire.\n\n- Un correctif."
)
NOTES_200 = (
    "Une majeure.\n\n**Mise en service.** Poser `ICECAST_MOUNT` dans `.env`,\n"
    "puis relancer.\n\n- Le reste."
)


def _release(version: str, notes: str = "", **extra) -> dict:
    return {
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/lazbutton/button/releases/tag/v{version}",
        "published_at": "2026-11-12T09:00:00Z",
        "body": notes or f"Les notes de la {version}.",
        "draft": False,
        "prerelease": False,
        **extra,
    }


class FakeGitHub:
    """L'API de GitHub : la version marquée « latest », puis la liste."""

    def __init__(self, latest: str = "1.3.0", listed: list[dict] | None = None):
        self.latest = latest
        self.listed = listed
        self.calls: list[str] = []
        self.status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        assert request.headers["User-Agent"].startswith("BUTTON/")
        if self.status != 200:
            return httpx.Response(self.status, json={"message": "non"})
        listed = self.listed or [_release(self.latest)]
        if request.url.path.endswith("/releases/latest"):
            found = next(
                item for item in listed if item["tag_name"] == f"v{self.latest}"
            )
            return httpx.Response(200, json=found)
        if request.url.path.endswith("/releases"):
            return httpx.Response(200, json=listed)
        return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture(autouse=True)
def _fresh_releases():
    updates.forget_releases()
    yield
    updates.forget_releases()


def _root(app_configration: dict) -> Path:
    return Path(app_configration["data"]["root"])


def _host(app_configration: dict, **state) -> None:
    """Ce que la commande station dit d'elle, comme le fait station requests."""
    raw = {
        "requests": "yes",
        "command": "1.2.0",
        "version": "1.2.0",
        "repo": "lazbutton/button",
        "hold": "",
        "updates": [],
        "nightly": "auto",
        "time": "04:00",
        "zone": "Europe/Paris",
        **state,
    }
    updates.record_host(_root(app_configration), raw)


async def _client(  # noqa: PLR0913
    app_configration, beets_integration, dbsession, users_password, name, github
):
    client = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, name
    )
    client.app.config["UPDATES_TRANSPORT"] = httpx.MockTransport(github)
    return client


async def test_updates_are_for_admins_only(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "majs-prog",
        {"live": True, "carts": True, "autodj": True},
    )
    assert (await client.get("/system/updates.json")).status_code == 403
    assert (await client.post("/system/updates/request.json")).status_code == 403
    assert (await client.delete("/system/updates/request.json")).status_code == 403
    assert not (_root(app_configration) / "updates" / "request.json").exists()


async def test_updates_without_the_host(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    # A station installed without the station command, or one older than the
    # button: the page says it, and the button does not ask.
    (_root(app_configration) / "versions.json").write_text(
        json.dumps({"recorded_at": "2026-11-12T03:01:07Z", "version": "1.2.0"})
    )
    github = FakeGitHub()
    client = await _client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "majs-sans",
        github,
    )
    result = await client.get("/system/updates.json")
    assert result.status_code == 200
    view = await result.get_json()
    assert view["installed"] == "1.2.0"
    assert view["latest"] == "1.3.0"
    assert view["host"] is None
    assert view["request"] is None
    assert view["blocked"]["code"] == "no_host"
    assert "sudo station update" in view["blocked"]["message"]
    asked = await client.post("/system/updates/request.json")
    assert asked.status_code == 409
    refused = await asked.get_json()
    assert refused["code"] == "no_host"
    assert refused["error"] == refused["message"]
    assert not (_root(app_configration) / "updates" / "request.json").exists()


async def test_updates_request_then_withdraw(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    _host(
        app_configration,
        updates=[
            "# Les mises à jour de station update",
            "1794452400\t1.1.0\t1.2.0\tfaite\t/opt/button/backups/b.tar\t"
            "redémarrée et contrôlée en 21 s",
        ],
    )
    github = FakeGitHub(
        "1.3.0",
        [_release("1.3.0", NOTES_130), _release("1.2.1"), _release("1.2.0")],
    )
    client = await _client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "majs-admin",
        github,
    )
    view = await (await client.get("/system/updates.json")).get_json()
    assert view["blocked"] is None
    assert view["installed"] == "1.2.0"
    # The versions the update brings, the newest first, with their notes.
    assert [item["version"] for item in view["releases"]] == ["1.3.0", "1.2.1"]
    assert view["releases"][0]["notes"] == NOTES_130
    assert view["releases"][0]["major"] is False
    assert view["major"] is None
    assert view["host"]["requests"] is True
    assert view["host"]["nightly"] == "auto"
    assert view["history"] == [
        {
            "started_at": "2026-11-12T04:00+01:00",
            "from": "1.1.0",
            "to": "1.2.0",
            "result": "done",
            "label": "faite",
            "detail": "redémarrée et contrôlée en 21 s",
        }
    ]

    asked = await client.post("/system/updates/request.json")
    assert asked.status_code == 202
    view = await asked.get_json()
    request = view["request"]
    assert request["state"] == "pending"
    assert request["requested_by"] == "majs-admin"
    assert (request["from"], request["target"]) == ("1.2.0", "1.3.0")
    assert request["unseen"] is False
    assert view["blocked"]["code"] == "open"
    # The host reads this file: its id and its state.
    stored = json.loads(
        (_root(app_configration) / "updates" / "request.json").read_text()
    )
    assert (stored["id"], stored["state"]) == (request["id"], "pending")

    again = await client.post("/system/updates/request.json")
    assert again.status_code == 409
    assert (await again.get_json())["code"] == "open"

    withdrawn = await client.delete("/system/updates/request.json")
    assert withdrawn.status_code == 200
    view = await withdrawn.get_json()
    assert view["request"] is None
    assert view["last"]["result"] == "withdrawn"
    assert view["last"]["detail"] == "Retirée par majs-admin."
    assert not (_root(app_configration) / "updates" / "request.json").exists()
    nothing = await client.delete("/system/updates/request.json")
    assert nothing.status_code == 409
    assert (await nothing.get_json())["code"] == "none"


async def test_updates_running_request_stays(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    _host(app_configration)
    client = await _client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "majs-encours",
        FakeGitHub(),
    )
    asked = await (await client.post("/system/updates/request.json")).get_json()
    root = _root(app_configration)
    assert updates.start(root, asked["request"]["id"])
    refused = await client.delete("/system/updates/request.json")
    assert refused.status_code == 409
    assert (await refused.get_json())["code"] == "running"
    view = await (await client.get("/system/updates.json")).get_json()
    assert view["request"]["state"] == "running"
    assert view["request"]["started_at"] is not None
    # The update done, the result stays for the page.
    assert updates.finish(
        root, asked["request"]["id"], "done", "en 18 s", ("1.2.0", "1.3.0")
    )
    view = await (await client.get("/system/updates.json")).get_json()
    assert view["request"] is None
    assert view["last"]["result"] == "done"
    assert (view["last"]["from"], view["last"]["to"]) == ("1.2.0", "1.3.0")


@pytest.mark.parametrize(
    ("state", "code", "said"),
    [
        ({"requests": "no"}, "requests_off", "--console-requests yes"),
        (
            {"hold": "Bloquées par station hold, le 12/11/2026.\nRaison : test"},
            "hold",
            "sudo station unhold",
        ),
        ({"version": "main", "command": "main"}, "main", "suit main"),
        ({"version": "1.3.0"}, "up_to_date", "1.3.0, la plus haute"),
    ],
)
async def test_updates_blocked_by_the_host(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    state: dict,
    code: str,
    said: str,
):
    _host(app_configration, **state)
    client = await _client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        f"majs-{code}",
        FakeGitHub(),
    )
    view = await (await client.get("/system/updates.json")).get_json()
    assert view["blocked"]["code"] == code
    assert said in view["blocked"]["message"]
    asked = await client.post("/system/updates/request.json")
    assert asked.status_code == 409
    assert (await asked.get_json())["code"] == code


async def test_updates_a_major_does_not_leave_from_here(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    _host(app_configration, version="1.2.0")
    github = FakeGitHub(
        "2.1.0",
        [_release("2.1.0"), _release("2.0.0", NOTES_200), _release("1.3.0")],
    )
    client = await _client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "majs-majeure",
        github,
    )
    view = await (await client.get("/system/updates.json")).get_json()
    assert view["blocked"]["code"] == "major"
    assert "la 2.0.0, une version majeure" in view["blocked"]["message"]
    assert "sudo station update --major" in view["blocked"]["message"]
    # Its « Mise en service », as the station command cites it.
    assert view["major"] == {
        "version": "2.0.0",
        "action": "Poser `ICECAST_MOUNT` dans `.env`,\npuis relancer.",
        "url": "https://github.com/lazbutton/button/releases/tag/v2.0.0",
    }
    assert [item["version"] for item in view["releases"]] == ["2.1.0", "2.0.0", "1.3.0"]
    assert [item["major"] for item in view["releases"]] == [False, True, False]
    assert (await client.post("/system/updates/request.json")).status_code == 409


async def test_updates_when_github_does_not_answer(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    _host(app_configration)
    github = FakeGitHub()
    github.status = 503
    client = await _client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "majs-github",
        github,
    )
    view = await (await client.get("/system/updates.json")).get_json()
    assert view["latest"] is None
    assert view["check"]["error"] == "GitHub répond 503"
    assert view["blocked"]["code"] == "latest_unknown"
    assert view["blocked"]["message"] == (
        "La dernière version ne se lit pas : GitHub répond 503."
    )
    # Asked again only after a while, or on refresh, once a minute at most.
    calls = len(github.calls)
    github.status = 200
    await client.get("/system/updates.json")
    await client.get("/system/updates.json?refresh=1")
    assert len(github.calls) == calls
    updates._releases["lazbutton/button"].fetched -= updates.FORCED_S + 1
    view = await (await client.get("/system/updates.json?refresh=1")).get_json()
    assert view["latest"] == "1.3.0"
    assert view["check"]["error"] is None
    assert view["blocked"] is None


async def test_updates_a_silent_host(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    _host(app_configration)
    path = _root(app_configration) / "updates" / "host.json"
    host = json.loads(path.read_text())
    host["seen_at"] = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    path.write_text(json.dumps(host))
    client = await _client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "majs-muette",
        FakeGitHub(),
    )
    view = await (await client.get("/system/updates.json")).get_json()
    assert view["blocked"]["code"] == "host_silent"
    assert "sudo station status" in view["blocked"]["message"]


def test_a_pending_request_the_host_does_not_look_at(tmp_path: Path):
    updates.record_host(tmp_path, {"requests": "yes", "version": "1.2.0"})
    request = updates.ask(tmp_path, "admin", "1.3.0", "1.2.0")
    now = datetime.now(UTC)
    assert updates.request_view(request, now)["unseen"] is False
    later = now + updates.UNSEEN + timedelta(seconds=1)
    assert updates.request_view(updates.read_request(tmp_path), later)["unseen"]
    # Looked at by the host: waiting, with why.
    assert updates.wait(tmp_path, request["id"], "QG, un direct, en cours")
    waiting = updates.read_request(tmp_path)
    assert waiting["waiting"] == "QG, un direct, en cours"
    assert updates.request_view(waiting, now + timedelta(seconds=30))["unseen"] is False


def test_the_host_turns_the_requests_off(tmp_path: Path):
    updates.record_host(tmp_path, {"requests": "yes", "version": "1.2.0"})
    request = updates.ask(tmp_path, "admin", "1.3.0", "1.2.0")
    assert updates.record_host(tmp_path, {"requests": "yes"})["id"] == request["id"]
    assert updates.record_host(tmp_path, {"requests": "no"}) is None
    last = updates.read_last(tmp_path)
    assert last["result"] == "refused"
    assert "coupées sur la machine" in last["detail"]
    # A running one stays: the host runs it.
    request = updates.ask(tmp_path, "admin", "1.3.0", "1.2.0")
    assert updates.start(tmp_path, request["id"])
    assert updates.record_host(tmp_path, {"requests": "no"})["state"] == "running"


def test_the_request_goes_back_to_pending(tmp_path: Path):
    request = updates.ask(tmp_path, "admin", "1.3.0", "1.2.0")
    assert not updates.start(tmp_path, "000000000000")
    assert updates.start(tmp_path, request["id"])
    # Started twice: no.
    assert not updates.start(tmp_path, request["id"])
    # Stopped by the window once its backup made: pending again.
    assert updates.wait(tmp_path, request["id"], "QG, commence à 20:00")
    back = updates.read_request(tmp_path)
    assert (back["state"], back["started_at"]) == ("pending", None)
    assert not updates.finish(tmp_path, "000000000000", "done", "")
    with pytest.raises(ValueError, match="perdu"):
        updates.finish(tmp_path, request["id"], "perdu", "")


def test_the_host_state_is_checked():
    state = updates.host_state(
        {
            "requests": "no",
            "version": "1.2.0; rm -rf /",
            "command": "main",
            "repo": "../../etc",
            "hold": "Bloquées\x1b[31m, le 12/11.\nRaison : essai",
            "updates": [
                "pas une ligne",
                "1762916400\t1.1.0\t1.2.0\tannulée\t-\tpendant le contrôle",
                "1762920000\tmain\t1.2.0\tretour arrière\t-\tà la main",
                12,
            ],
            "nightly": "jamais",
            "time": "4h",
            "zone": "Europe/Paris",
        }
    )
    assert state["requests"] is False
    assert state["version"] is None
    assert state["command"] == "main"
    assert state["repo"] == "lazbutton/button"
    assert state["hold"] == "Bloquées[31m, le 12/11.\nRaison : essai"
    assert [(item["from"], item["result"]) for item in state["history"]] == [
        ("main", "rollback"),
        ("1.1.0", "rolled_back"),
    ]
    assert (state["nightly"], state["time"], state["zone"]) == (
        None,
        None,
        "Europe/Paris",
    )


def test_major_action_reads_the_paragraph():
    assert updates.major_action(NOTES_200) == (
        "Poser `ICECAST_MOUNT` dans `.env`,\npuis relancer."
    )
    assert updates.major_action("- Rien.\n") is None
    fenced = "```\n**Mise en service.** non\n```\n\n**Mise en service.** Oui."
    assert updates.major_action(fenced) == "Oui."


def test_the_results_of_the_command_are_those_of_the_service():
    from radiotomate.commands.maintenance import updates_finish

    choices = next(
        param for param in updates_finish.params if param.name == "result"
    ).type.choices
    assert tuple(choices) == updates.RESULTS
