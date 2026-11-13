"""
The sounds of the antenna bench, and its RTCONFIG.

    python sounds.py <folder>

Each sound is a sweep: two tones whose pitch keeps moving. No 20 ms frame
resembles the next one, so a frame the playout airs twice can only be a stall.
The titles and the jingle are MP3, as most of the music of a station: lame
encodes them. Standard library only otherwise.
"""

from __future__ import annotations

import math
import random
import subprocess
import sys
import wave
from array import array
from pathlib import Path

RATE = 44100

# name: seconds, then start pitch and slope (Hz, Hz/s) of each of the two tones.
SOUNDS = {
    "start": (1.0, 440.0, 60.0, 880.0, -40.0),
    # Long enough for a stall: the crossfade once froze this queue ten to
    # twenty seconds into its first title.
    "title-1": (40.0, 300.0, 9.0, 900.0, -7.0),
    "title-2": (7.0, 520.0, 11.0, 1500.0, -9.0),
    "title-3": (7.0, 760.0, 13.0, 2100.0, -11.0),
    "title-4": (7.0, 1010.0, 6.0, 2600.0, -5.0),
    "title-5": (20.0, 420.0, 7.0, 1800.0, -8.0),
    "title-6": (20.0, 610.0, 5.0, 2300.0, -6.0),
    "jingle": (2.5, 2500.0, 40.0, 4000.0, -30.0),
    "cart": (5.0, 1700.0, 25.0, 3300.0, -20.0),
}
# The start sound of a station is a WAV: this one stays so.
MP3 = [name for name in SOUNDS if name != "start"]
# Titles 5 and 6 are VBR, without the Xing header that gives the length of the
# file, as some files a station receives: ffmpeg then estimates the length from
# the bitrate of the first frames. Their parts, as (seconds, level of the tones,
# level of a noise the encoder spends its bits on): loud then silent, announced
# too short; silent then loud, announced too long. Silent for less than the
# 10 s the music queue lets pass.
SHAPES = {
    "title-5": [(12.0, 1.0, 0.3), (8.0, 0.0, 0.0)],
    "title-6": [(8.0, 0.0, 0.0), (12.0, 1.0, 0.3)],
}

RTCONFIG = """\
---
# The antenna bench: the outputs of a station, test passwords.
playout_process_config:
    input_name: "stream"
    input_min_buffer: 5.
    input_max_buffer: 30.
    token: {token}
    start_sound: {folder}/start.wav
    outputs:
        - driver: icecast
          encoder: mp3cbr
          quality: 128
          host: icecast
          port: 8000
          mount: radio.mp3
          password: antenne-source
        - driver: icecast
          encoder: wav
          quality: 1
          host: icecast
          port: 8000
          mount: studio.wav
          password: antenne-source

metadata_log:
    extra_fields:
        - genre
        - year
"""

TOKEN = "jeton-du-banc"


def sweep(  # noqa: PLR0913
    seconds: float,
    f1: float,
    k1: float,
    f2: float,
    k2: float,
    shape: list[tuple[float, float, float]] | None = None,
) -> array:
    """Stereo, 16 bits: the right channel a little off the left one. A shape
    sets the level of each part, and adds its noise."""
    samples = array("h")
    two_pi = 2.0 * math.pi
    noise = random.Random(int(f1))
    index = 0
    for part, tone, hiss in shape or [(seconds, 1.0, 0.0)]:
        for _ in range(int(part * RATE)):
            t = index / RATE
            low = two_pi * (f1 + k1 * t) * t
            high = two_pi * (f2 + k2 * t) * t
            left = tone * (0.35 * math.sin(low) + 0.2 * math.sin(high))
            right = tone * (0.35 * math.sin(low * 1.07) + 0.2 * math.sin(high * 0.95))
            if hiss:
                left += hiss * (2.0 * noise.random() - 1.0)
                right += hiss * (2.0 * noise.random() - 1.0)
            samples.append(int(left * 32767))
            samples.append(int(right * 32767))
            index += 1
    return samples


def audible(name: str) -> float:
    """The seconds of a sound that are not silence."""
    shape = SHAPES.get(name)
    if not shape:
        return SOUNDS[name][0]
    return sum(part for part, tone, hiss in shape if tone or hiss)


def lame_options(name: str) -> list[str]:
    if name in SHAPES:
        # VBR, and -t: no Xing header.
        return ["-V", "0", "-t"]
    return ["--cbr", "-b", "192"]


def write(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, tones in SOUNDS.items():
        samples = sweep(*tones, shape=SHAPES.get(name))
        if sys.byteorder == "big":
            samples.byteswap()
        wav = folder / f"{name}.wav"
        with wave.open(str(wav), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(samples.tobytes())
        if name in MP3:
            subprocess.run(
                [
                    "lame",
                    "--quiet",
                    *lame_options(name),
                    str(wav),
                    str(folder / f"{name}.mp3"),
                ],
                check=True,
            )
            wav.unlink()
    (folder / "radiotomate.yaml").write_text(
        RTCONFIG.format(token=TOKEN, folder=folder), encoding="utf-8"
    )


if __name__ == "__main__":
    write(Path(sys.argv[1]))
