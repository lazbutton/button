"""
Encoder tokens: an encoder logs in to the harbor with its account's username and
token, so that the account password doesn't sit in the encoder's settings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from radiotomate.domain.agenda import iso_paris
from radiotomate.models import Setting, User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

_log = logging.getLogger(__name__)

SETTING_ACCOUNT_PASSWORD = "features.allow_account_password"
SETTING_OFF = {"0", "false", "off", ""}


async def account_password_allowed(session: ormSession) -> bool:
    """
    Whether the harbor still takes the account password. A missing key keeps it, so
    that no encoder of an existing station is cut: a new installation turns it off.
    """
    row = await Setting.from_key(session, SETTING_ACCOUNT_PASSWORD)
    return row is None or str(row.value).strip().lower() not in SETTING_OFF


async def encoder_login(session: ormSession, username: str, secret: str) -> User | None:
    """
    The account an encoder logs in as: `secret` is its token, or the account password
    while the station allows it.
    """
    user = await User.from_username(session, username)
    if user and user.check_stream_token(secret):
        return user
    if not await account_password_allowed(session):
        return None
    user = await User.check(session, username, secret)
    if user:
        _log.warning(
            "%s logged in to the harbor with the account password: give the encoder "
            "its token before turning %s off",
            username,
            SETTING_ACCOUNT_PASSWORD,
        )
    return user


def stream_token_payload(user: User) -> dict:
    return {"created_at": iso_paris(user.stream_token_created_at)}
