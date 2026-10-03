"""Persistent daily speech recordings and transcripts."""

import json
import subprocess
import tempfile
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np

from config.settings import Config
from asr.transcriber import TranscriptSegment
from vad.silero_vad import SpeechSegment
from utils.logger import logger


class DailyJournal:
    """Append speech segments to one recording and transcript per local day."""

    def __init__(self, config: Config):
        self.config = config
        self.timezone = ZoneInfo(config.journal.timezone)
        self.root = Path(config.journal.storage_path)
        self.audio_dir = self.root / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(config.database.path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_journals (
                    date TEXT PRIMARY KEY,
                    audio_path TEXT NOT NULL,
                    transcript TEXT NOT NULL DEFAULT '',
                    start_time TEXT,
                    end_time TEXT,
                    speech_seconds REAL NOT NULL DEFAULT 0,
                    segment_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def local_date(self, timestamp: datetime) -> str:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=self.timezone)
        return timestamp.astimezone(self.timezone).strftime("%Y-%m-%d")

    def record(self, segment: SpeechSegment, transcript: Optional[TranscriptSegment]) -> str:
        """Append a VAD segment and its transcript to the appropriate day."""
        import sqlite3

        day = self.local_date(segment.start_time)
        wav_path = self.audio_dir / f"{day}.wav"
        mp3_path = self.audio_dir / f"{day}.mp3"
        self._append_wav(wav_path, segment.audio, segment.sample_rate)
        self._encode_mp3(wav_path, mp3_path)

        line = ""
        if transcript and transcript.text.strip():
            local_start = segment.start_time.astimezone(self.timezone)
            line = f"[{local_start:%H:%M:%S}] ({transcript.language}) {transcript.text.strip()}"

        now = datetime.now(self.timezone).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT transcript, speech_seconds, segment_count, start_time FROM daily_journals WHERE date = ?",
                (day,),
            ).fetchone()
            transcript_text = "\n".join(filter(None, [(row[0] if row else ""), line]))
            start_time = row[3] if row and row[3] else segment.start_time.isoformat()
            conn.execute(
                """
                INSERT INTO daily_journals
                    (date, audio_path, transcript, start_time, end_time,
                     speech_seconds, segment_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    audio_path=excluded.audio_path,
                    transcript=excluded.transcript,
                    end_time=excluded.end_time,
                    speech_seconds=excluded.speech_seconds,
                    segment_count=excluded.segment_count,
                    updated_at=excluded.updated_at
                """,
                (
                    day,
                    str(mp3_path),
                    transcript_text,
                    start_time,
                    segment.end_time.isoformat(),
                    (row[1] if row else 0) + segment.duration_seconds,
                    (row[2] if row else 0) + 1,
                    now,
                ),
            )
        return day

    @staticmethod
    def _append_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
        audio = np.asarray(audio).reshape(-1)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        if path.exists():
            with wave.open(str(path), "ab") as output:
                output.writeframes(pcm)
            return
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(pcm)

    @staticmethod
    def _encode_mp3(wav_path: Path, mp3_path: Path) -> None:
        with tempfile.NamedTemporaryFile(
            dir=mp3_path.parent, prefix=f".{mp3_path.stem}.", suffix=".mp3", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
                    "-codec:a", "libmp3lame", "-b:a", "64k", str(temporary_path),
                ],
                check=True,
                timeout=120,
            )
            temporary_path.replace(mp3_path)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            temporary_path.unlink(missing_ok=True)
            logger.error("Failed to encode daily MP3 %s: %s", mp3_path, exc)
            raise RuntimeError(f"Unable to encode daily MP3: {mp3_path}") from exc
