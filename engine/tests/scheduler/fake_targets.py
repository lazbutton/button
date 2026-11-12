"""A fake SMTP server and a fake ntfy, on this machine, for the alerts' tests.

``FakeSMTP`` speaks enough SMTP for smtplib and curl: EHLO, STARTTLS, AUTH
PLAIN and LOGIN, MAIL, RCPT, DATA, QUIT. Its modes: ``starttls``, which
offers AUTH only once in TLS, like a submission server on port 587; ``smtps``,
in TLS from the first byte, like port 465; ``plain``, a server without TLS,
which offers AUTH in clear, and that a client must refuse.

``FakeNtfy`` takes ntfy's JSON, posted to its root, or a message posted to a
topic with ntfy's headers, and keeps what it receives. A token makes it
refuse a request without it, and ``failing`` makes it answer 500.

Alone, they serve a bench, until Ctrl-C, and write what they receive, one JSON
line each, to the file given::

    python fake_targets.py --smtp 2525 --ntfy 8080 --certs DIR --out FILE

``--smtp-mode``, ``--smtp-user``, ``--smtp-password`` and ``--ntfy-token``
change what the fakes expect.
"""

from __future__ import annotations

import argparse
import base64
import json
import socketserver
import ssl
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from email import message_from_bytes, policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Callable
    from email.message import EmailMessage


def make_certificate(folder: Path) -> tuple[Path, Path]:
    """A self-signed certificate for localhost and 127.0.0.1, made by openssl."""
    folder.mkdir(parents=True, exist_ok=True)
    cert, key = folder / "cert.pem", folder / "key.pem"
    if not cert.exists():
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "2",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
    return cert, key


def client_context(cert: Path) -> ssl.SSLContext:
    """What a client trusts to reach the fake: its certificate only."""
    return ssl.create_default_context(cafile=str(cert))


@dataclass
class Mail:
    sender: str
    recipients: list[str]
    data: bytes
    user: str | None
    tls: bool

    @property
    def message(self) -> EmailMessage:
        return message_from_bytes(self.data, policy=policy.default)


class _SMTPHandler(socketserver.StreamRequestHandler):
    def setup(self) -> None:
        self.tls = False
        if self.fake.mode == "smtps":
            self.request = self.fake.context.wrap_socket(self.request, server_side=True)
            self.connection = self.request
            self.tls = True
        super().setup()

    def reply(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode())
        self.wfile.flush()

    def read(self) -> str | None:
        raw = self.rfile.readline()
        if not raw:
            return None
        return raw.decode("utf-8", "replace").rstrip("\r\n")

    def credentials(self, argument: str) -> tuple[str, str] | None:
        mechanism, _, initial = argument.partition(" ")
        mechanism = mechanism.upper()
        if mechanism == "PLAIN":
            if not initial:
                self.reply("334 ")
                initial = self.read() or ""
            parts = base64.b64decode(initial).split(b"\0")
            if len(parts) != 3:
                return None
            return parts[1].decode(), parts[2].decode()
        if mechanism == "LOGIN":
            if not initial:
                self.reply("334 VXNlcm5hbWU6")
                initial = self.read() or ""
            name = base64.b64decode(initial).decode()
            self.reply("334 UGFzc3dvcmQ6")
            secret = base64.b64decode(self.read() or "").decode()
            return name, secret
        return None

    def handle(self) -> None:
        self.user: str | None = None
        self.sender = ""
        self.recipients: list[str] = []
        self.reply("220 faux-smtp.localhost ESMTP")
        while (line := self.read()) is not None:
            verb, _, argument = line.partition(" ")
            self.fake.commands.append(verb.upper())
            answer = getattr(self, f"on_{verb.lower()}", None)
            if answer is None:
                self.reply("502 5.5.2 Error: command not recognized")
            elif answer(argument) == "quit":
                return

    @property
    def fake(self) -> FakeSMTP:
        return self.server.fake  # type: ignore[attr-defined]

    @property
    def can_auth(self) -> bool:
        return self.tls or self.fake.mode == "plain"

    def on_ehlo(self, _argument: str) -> None:
        offers = ["faux-smtp.localhost", "8BITMIME"]
        if self.fake.mode == "starttls" and not self.tls:
            offers.append("STARTTLS")
        if self.can_auth:
            offers.append("AUTH PLAIN LOGIN")
        for offer in offers[:-1]:
            self.reply("250-" + offer)
        self.reply("250 " + offers[-1])

    on_helo = on_ehlo

    def on_starttls(self, _argument: str) -> None:
        if self.fake.mode != "starttls" or self.tls:
            self.reply("502 5.5.1 STARTTLS not available")
            return
        self.reply("220 2.0.0 TLS")
        self.request = self.fake.context.wrap_socket(self.request, server_side=True)
        self.connection = self.request
        self.rfile = self.request.makefile("rb")
        self.wfile = self.request.makefile("wb")
        self.tls = True

    def on_auth(self, argument: str) -> None:
        if not self.can_auth:
            self.reply("538 5.7.11 Encryption required")
            return
        given = self.credentials(argument)
        self.fake.logins.append(given)
        if given == (self.fake.user, self.fake.password):
            self.user = given[0]
            self.reply("235 2.7.0 Authentication successful")
        else:
            self.reply("535 5.7.8 Authentication credentials invalid")

    def on_mail(self, argument: str) -> None:
        if self.fake.user and self.user is None:
            self.reply("530 5.7.0 Authentication required")
            return
        self.sender = argument.partition(":")[2].strip().split(" ")[0].strip("<>")
        self.recipients = []
        self.reply("250 2.1.0 Ok")

    def on_rcpt(self, argument: str) -> None:
        self.recipients.append(argument.partition(":")[2].strip().strip("<>"))
        self.reply("250 2.1.5 Ok")

    def on_data(self, _argument: str) -> None:
        self.reply("354 End data with <CR><LF>.<CR><LF>")
        lines = []
        while (raw := self.rfile.readline()) not in (b".\r\n", b".\n", b""):
            lines.append(raw[1:] if raw.startswith(b"..") else raw)
        mail = Mail(
            self.sender, list(self.recipients), b"".join(lines), self.user, self.tls
        )
        self.fake.mails.append(mail)
        self.fake.received(asdict(mail) | {"kind": "mail"})
        self.reply("250 2.0.0 Ok: queued")

    def on_rset(self, _argument: str) -> None:
        self.sender, self.recipients = "", []
        self.reply("250 2.0.0 Ok")

    def on_noop(self, _argument: str) -> None:
        self.reply("250 2.0.0 Ok")

    def on_quit(self, _argument: str) -> str:
        self.reply("221 2.0.0 Bye")
        return "quit"


class _SMTPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class FakeSMTP:
    def __init__(  # noqa: PLR0913
        self,
        mode: str = "starttls",
        certificate: tuple[Path, Path] | None = None,
        user: str = "alertes@radio.example",
        password: str = "mot-de-passe-de-test",
        port: int = 0,
        on_receive: Callable[[dict], None] | None = None,
    ):
        self.mode = mode
        self.user = user
        self.password = password
        self.mails: list[Mail] = []
        self.logins: list[tuple[str, str] | None] = []
        self.commands: list[str] = []
        self.on_receive = on_receive
        self.context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        if certificate is not None:
            self.context.load_cert_chain(*map(str, certificate))
        self.server = _SMTPServer(("127.0.0.1", port), _SMTPHandler)
        self.server.fake = self  # type: ignore[attr-defined]
        self.port = self.server.server_address[1]

    def received(self, record: dict) -> None:
        if self.on_receive is not None:
            self.on_receive(record)

    def __enter__(self) -> Self:
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *_) -> None:
        self.server.shutdown()
        self.server.server_close()


class _NtfyHandler(BaseHTTPRequestHandler):
    def log_message(self, *_) -> None:
        return

    # The names of http.server's handlers.
    def do_POST(self) -> None:  # noqa: N802
        fake: FakeNtfy = self.server.fake  # type: ignore[attr-defined]
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if fake.token and self.headers.get("Authorization") != f"Bearer {fake.token}":
            self.answer(403, {"code": 40301, "error": "forbidden"})
            return
        if fake.failing:
            self.answer(500, {"error": "panne"})
            return
        if self.path == "/":
            message = json.loads(body)
        else:
            message = {
                "topic": self.path.strip("/"),
                "message": body.decode(),
                "title": self.headers.get("Title", ""),
                "priority": self.headers.get("Priority", ""),
                "tags": self.headers.get("Tags", ""),
            }
        message["authorization"] = self.headers.get("Authorization", "")
        fake.messages.append(message)
        fake.received(message | {"kind": "ntfy"})
        self.answer(200, {"id": str(len(fake.messages)), "event": "message"})

    do_PUT = do_POST  # noqa: N815

    def answer(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FakeNtfy:
    def __init__(
        self,
        token: str = "",
        port: int = 0,
        on_receive: Callable[[dict], None] | None = None,
    ):
        self.token = token
        self.failing = False
        self.messages: list[dict] = []
        self.on_receive = on_receive
        self.server = ThreadingHTTPServer(("127.0.0.1", port), _NtfyHandler)
        self.server.daemon_threads = True
        self.server.fake = self  # type: ignore[attr-defined]
        self.port = self.server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def received(self, record: dict) -> None:
        if self.on_receive is not None:
            self.on_receive(record)

    def __enter__(self) -> Self:
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *_) -> None:
        self.server.shutdown()
        self.server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--smtp", type=int, default=2525)
    parser.add_argument("--smtp-mode", default="starttls")
    parser.add_argument("--smtp-user", default="alertes@radio.example")
    parser.add_argument("--smtp-password", default="mot-de-passe-de-test")
    parser.add_argument("--ntfy", type=int, default=8080)
    parser.add_argument("--ntfy-token", default="")
    parser.add_argument("--certs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    options = parser.parse_args()
    lock = threading.Lock()

    def write(record: dict) -> None:
        if isinstance(record.get("data"), bytes):
            record["data"] = record["data"].decode("utf-8", "replace")
        with lock, options.out.open("a") as out:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    certificate = make_certificate(options.certs)
    with (
        FakeSMTP(
            options.smtp_mode,
            certificate,
            options.smtp_user,
            options.smtp_password,
            options.smtp,
            write,
        ),
        FakeNtfy(options.ntfy_token, port=options.ntfy, on_receive=write),
    ):
        sys.stdout.write(
            f"SMTP {options.smtp} ({options.smtp_mode}), ntfy {options.ntfy}\n"
        )
        sys.stdout.flush()
        threading.Event().wait()


if __name__ == "__main__":
    main()
