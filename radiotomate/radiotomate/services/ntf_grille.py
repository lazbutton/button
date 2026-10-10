"""Grille NTF : jour habillé, nuit en nappe, habillage de remplacement.

Les fichiers audio sont des tons courts, clairement nommés REMPLACANT.
Ils tiennent la place des jingles, virgules et archives tant que le
collectif n'a pas déposé les éditions 1 à 3.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.enums import CartMode, ScheduleMode
from radiotomate.models import AutoDJSlot, Cart, Clock, MusicCategory, Sound, User
from radiotomate.models.cart import JINGLES_QUEUE
from radiotomate.services.autodj import apply_clock, create_clock, save_slot

JOUR = "Jour habillé"
NUIT = "Nuit nappe"
JINGLES = "Jingles"
VIRGULES = "Virgules"
ARCHIVES = "Archives NTF"
COLOR_JOUR = "#c45c26"
COLOR_NUIT = "#1e3a5f"
JOUR_MINUTE = 7 * 60
PUBS_MINUTE = 10 * 60
SOIR_MINUTE = 18 * 60


def write_tone(path: Path, freq: float, seconds: float, rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = int(rate * seconds)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for index in range(count):
            envelope = 1.0
            if index < rate // 20:
                envelope = index / (rate // 20)
            elif index > count - rate // 10:
                envelope = max(0.0, (count - index) / (rate // 10))
            sample = int(9000 * envelope * math.sin(2 * math.pi * freq * index / rate))
            frames += struct.pack("<hh", sample, sample)
        handle.writeframes(frames)


def write_placeholders(media: Path) -> dict[str, list[Path]]:
    """Tons de remplacement dans l'arbre de la banque. Idempotent."""
    jingles = media / "30-habillage" / "jingles"
    stings = media / "30-habillage" / "stings"
    archives = {
        "ntf1": media / "20-archives" / "ntf1",
        "ntf2": media / "20-archives" / "ntf2",
        "ntf3": media / "20-archives" / "ntf3",
    }
    written: dict[str, list[Path]] = {"jingles": [], "virgules": [], "archives": []}
    for index, freq in enumerate((523, 659, 784), start=1):
        path = jingles / f"REMPLACANT - Jingle {index}.wav"
        write_tone(path, freq, 2.8)
        written["jingles"].append(path)
    for index, freq in enumerate((988, 1175, 1319), start=1):
        path = stings / f"REMPLACANT - Virgule {index}.wav"
        write_tone(path, freq, 0.7)
        written["virgules"].append(path)
    for edition, folder in archives.items():
        for index, freq in enumerate((196, 247), start=1):
            path = folder / f"REMPLACANT - {edition.upper()} archive {index}.wav"
            write_tone(path, freq, 20.0)
            written["archives"].append(path)
    return written


async def _ensure_category(session: ormSession) -> MusicCategory:
    category = await MusicCategory.from_name(session, ARCHIVES)
    if category is None:
        category = MusicCategory(
            name=ARCHIVES,
            query="genre:Archive",
            empty_query="grouping:rotation",
        )
        session.add(category)
        await session.flush()
    return category


async def _ensure_cart(session: ormSession, title: str, folder: Path) -> Cart:
    cart = await Cart.from_title(session, title)
    if cart is None:
        cart = Cart(
            title=title,
            path=folder,
            url=JINGLES_QUEUE,
            notes="Habillage NTF de remplacement, en attendant les fichiers du camp.",
            mode=CartMode.RANDOM,
            schedule_mode=ScheduleMode.CLOCK,
            max_duration=0,
        )
        session.add(cart)
        await session.flush()
    return cart


async def _ensure_sound(
    session: ormSession,
    cart: Cart,
    path: Path,
    uploader_id: int,
    seconds: int,
) -> None:
    existing = await Sound.from_media_path(session, str(path))
    if existing is not None:
        return
    rank = 1 + len(list(await session.scalars(select(Sound).where(Sound.cart_id == cart.id))))
    session.add(
        Sound(
            cart_id=cart.id,
            rank=rank,
            path=path,
            duration=seconds,
            title=path.stem,
            active=True,
            gain=0.0,
            peak=1.0,
            uploader_id=uploader_id,
        )
    )


async def _ensure_clock(session: ormSession, payload: dict) -> Clock:
    clock = await Clock.from_name(session, payload["name"])
    if clock is None:
        clock = await create_clock(session, payload)
    else:
        payload = {**payload, "version": clock.version}
        clock = await apply_clock(session, clock, payload, creating=False)
    await session.flush()
    return await Clock.from_name(session, payload["name"])


async def _point_slot(
    session: ormSession,
    *,
    day: int,
    minute: int,
    title: str,
    color: str,
    clock_id: int,
) -> None:
    slot = await AutoDJSlot.from_time(session, minute, day_of_week=day, exact=True)
    if slot is None:
        slot = AutoDJSlot(constraints={"filters": [], "totalweight": 0})
        session.add(slot)
        await save_slot(
            session,
            slot,
            title=title,
            color=color,
            day_of_week=day,
            minute=minute,
            clock_id=clock_id,
        )
        return
    slot.title = title
    slot.color = color
    slot.clock_id = clock_id


async def apply_ntf_grille(session: ormSession, media: Path) -> dict[str, str]:
    """Pose la grille et les sons de remplacement. Rejouable."""
    files = write_placeholders(media)
    user = await session.scalar(select(User).order_by(User.id).limit(1))
    if user is None:
        raise RuntimeError("Aucun compte : créez-en un avant la grille NTF.")
    await _ensure_category(session)
    jingles = await _ensure_cart(session, JINGLES, media / "30-habillage" / "jingles")
    virgules = await _ensure_cart(session, VIRGULES, media / "30-habillage" / "stings")
    for path in files["jingles"]:
        await _ensure_sound(session, jingles, path, user.id, seconds=3)
    for path in files["virgules"]:
        await _ensure_sound(session, virgules, path, user.id, seconds=1)
    await session.flush()

    jour = await _ensure_clock(
        session,
        {
            "name": JOUR,
            "fallback_cart": JINGLES,
            "motif": [
                {"kind": "jingle", "cart": JINGLES},
                {"kind": "musique", "category": "Rotation"},
                {"kind": "musique", "category": "Rotation"},
                {"kind": "musique", "category": "Rotation"},
            ],
            "anchors": [
                {"kind": "jingle", "cart": JINGLES, "minute": 0, "sync": "dure"},
            ],
        },
    )
    nuit = await _ensure_clock(
        session,
        {
            "name": NUIT,
            "fallback_cart": JINGLES,
            "motif": [
                {"kind": "jingle", "cart": VIRGULES},
                *({"kind": "musique", "category": ARCHIVES} for _ in range(6)),
            ],
            "anchors": [
                {"kind": "jingle", "cart": VIRGULES, "minute": 0, "sync": "molle"},
            ],
        },
    )
    for day in range(7):
        await _point_slot(
            session,
            day=day,
            minute=0,
            title=NUIT,
            color=COLOR_NUIT,
            clock_id=nuit.id,
        )
        for minute in (JOUR_MINUTE, PUBS_MINUTE, SOIR_MINUTE):
            await _point_slot(
                session,
                day=day,
                minute=minute,
                title=JOUR,
                color=COLOR_JOUR,
                clock_id=jour.id,
            )
    await session.flush()
    return {"jour": jour.name, "nuit": nuit.name, "media": str(media)}
