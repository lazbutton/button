from collections.abc import Coroutine
from contextlib import ExitStack
from pathlib import Path
from time import time_ns

import quart
from multipart import (
    MultiDict,
    MultipartError,
    MultipartSegment,
    PushMultipartParser,
    parse_options_header,
)
from werkzeug.exceptions import BadRequest

_allowed_chars = ("-", ".", "_")
_unreadable_upload = (
    "Un fichier n'a pas de nom lisible : son nom finit peut-être par « \\ ». "
    "Renomme-le, puis envoie-le à nouveau."
)
_malformed_upload = (
    "L'envoi est arrivé incomplet ou mal formé. Envoie les fichiers à nouveau."
)


def safe_path(basedir: Path, filename: str, prefix: str = "") -> Path:
    """
    Generates a complete path in `basedir` from `filename`,
    and ensures nothing already exists there.
    Keeps only alphanumeric characters and the characters in _allowed_chars,
    also prefix the files with `prefix`, or 4 random digits to avoid collisions.
    """
    if not basedir:
        raise ValueError("Missing basedir")
    safe_filename = "".join(c for c in filename if c.isalnum() or c in _allowed_chars)
    while True:
        target_path = basedir / (prefix + safe_filename)
        if not target_path.exists():
            return target_path
        prefix = str(time_ns())[-4:]


def safe_int(s: str | None, default: int | None, positive=False) -> int | None:
    """
    Parses given string (extracted from a form dict) to an integer. Returns `default`
    if the value cannot be parsed to an integer. When `positive=True`, returned
    `default` if parsed value is negative.
    """
    if s is None:
        return default
    try:
        parsed = int(s)
        if positive and parsed < 0:
            return default
        else:
            return parsed
    except ValueError:
        return default


async def stream_form(  # noqa: PLR0912
    base_path: Path | None = None,
    file_fields: tuple[str, ...] = (),
) -> Coroutine[None, None, MultiDict]:
    """
    Reads the multipart form of the request: writes its files in `base_path`, and
    returns its fields. A part named in `file_fields` must be a file.
    A malformed form is refused with BadRequest, and a form refused or cut short
    keeps none of its files.
    """
    header = quart.request.headers.get("Content-Type", "")
    content_type, options = parse_options_header(header)
    boundary = options.get("boundary")
    if not boundary:
        raise BadRequest(_malformed_upload)
    form_fields = MultiDict()
    current_form_field = None
    current_file = None
    written_paths = []
    try:
        with ExitStack() as stack:
            parser = PushMultipartParser(boundary, strict=True)
            stack.enter_context(parser)

            async for chunk in quart.request.body:
                for result in parser.parse(chunk):
                    if isinstance(result, MultipartSegment):
                        if result.filename:
                            target_path = safe_path(base_path, result.filename)
                            current_file = target_path.open("wb", buffering=1024 * 1024)
                            stack.enter_context(current_file)
                            written_paths.append(target_path)
                            form_fields[result.name] = {
                                "filename": result.filename,
                                "content_type": result.content_type,
                                "uploaded_to": target_path,
                            }
                        elif result.name in file_fields:
                            # No filename at all: a text field, or a name that
                            # multipart cannot read, such as `son\` since 1.3.1.
                            # An empty one is an empty file input: nothing to keep.
                            if result.filename is None:
                                raise BadRequest(_unreadable_upload)
                        else:
                            current_form_field = result.name
                    elif result:  # Result is a non-empty bytearray
                        if current_form_field:
                            try:
                                form_fields[current_form_field] = result.decode()
                            except UnicodeDecodeError as exc:
                                # Not text: most likely a file whose name
                                # multipart cannot read.
                                raise BadRequest(_unreadable_upload) from exc
                        elif current_file is not None:
                            current_file.write(result)
                    else:  # end of segment
                        current_form_field = None
                        current_file = None
                if parser.closed:
                    break
    except BaseException as exc:
        # Refused or cut short: keep none of the form's files.
        for path in written_paths:
            path.unlink(missing_ok=True)
        if isinstance(exc, MultipartError):
            raise BadRequest(_malformed_upload) from exc
        raise
    return form_fields
