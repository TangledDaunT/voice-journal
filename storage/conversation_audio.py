"""Assemble verified clips on their original timeline; excluded gaps become silence."""

import hashlib
import numpy as np
import subprocess
import wave
from datetime import datetime
from pathlib import Path


def conversation_audio(rows, variant, config):
    root = Path(config.database.path).parent.parent.resolve()
    fingerprint = hashlib.sha256(str(("declick-v2", [(r["id"], r["end_ts"], r["audio_path"], r["clean_path"]) for r in rows])).encode()).hexdigest()[
        :20
    ]
    directory = Path(config.dashboard.audio_cache_path) / "conversations"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{rows[0]['conversation_id']}-{variant}-{fingerprint}.wav"
    if target.exists():
        return target
    temporary = target.with_suffix(".tmp.wav")
    rate = 16000
    origin = datetime.fromisoformat(rows[0]["start_ts"])
    cursor = 0
    try:
        with wave.open(str(temporary), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            for index, row in enumerate(rows):
                path = Path(row["clean_path"] if variant == "clean" else row["audio_path"])
                if not path.is_file() or not path.resolve().is_relative_to(root):
                    raise ValueError("A conversation clip is unavailable")
                offset = round(
                    (datetime.fromisoformat(row["start_ts"]) - origin).total_seconds() * rate
                )
                if offset > cursor:
                    output.writeframes(b"\0\0" * (offset - cursor))
                    cursor = offset
                pcm = subprocess.run(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-i",
                        str(path),
                        "-f",
                        "s16le",
                        "-ar",
                        str(rate),
                        "-ac",
                        "1",
                        "-",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=30,
                ).stdout
                # Keep sample ownership exact even if a codec has padding or legacy clips overlap.
                expected = round(
                    (
                        datetime.fromisoformat(row["end_ts"])
                        - datetime.fromisoformat(row["start_ts"])
                    ).total_seconds()
                    * rate
                )
                pcm = pcm[: expected * 2]
                skip = max(0, cursor - offset)
                pcm = pcm[skip * 2 :]
                samples = np.frombuffer(pcm, dtype="<i2").copy()
                fade = min(80, len(samples) // 2)
                previous_end = datetime.fromisoformat(rows[index - 1]["end_ts"]) if index else None
                next_start = datetime.fromisoformat(rows[index + 1]["start_ts"]) if index + 1 < len(rows) else None
                if fade and (previous_end is None or (datetime.fromisoformat(row["start_ts"]) - previous_end).total_seconds() > .025):
                    samples[:fade] = samples[:fade] * np.linspace(0, 1, fade)
                if fade and (next_start is None or (next_start - datetime.fromisoformat(row["end_ts"])).total_seconds() > .025):
                    samples[-fade:] = samples[-fade:] * np.linspace(1, 0, fade)
                output.writeframes(samples.tobytes())
                cursor += len(samples)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
