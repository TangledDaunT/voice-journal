"""Groq-only cloud transcription with durable conservative quota accounting."""

import io
import json
import os
import time
import wave
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import requests


class GroqUnavailableError(RuntimeError):
    pass


class GroqDeferredError(GroqUnavailableError):
    def __init__(self, message, retry_after=5):
        super().__init__(message)
        self.retry_after = retry_after


class GroqClient:
    endpoint = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(self, config, store, session=None):
        self.config = config
        self.store = store
        self.session = session or requests.Session()

    def reserve(self, seconds):
        now = time.time()
        day = datetime.fromtimestamp(now, ZoneInfo("Asia/Kolkata")).date().isoformat()
        billed = max(10.0, seconds)
        caps = self.config.transcription
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cooldown = conn.execute(
                "SELECT value FROM service_state WHERE key='groq_retry_at'"
            ).fetchone()
            if cooldown and float(cooldown[0]) > now:
                raise GroqUnavailableError("Groq cooling down after a rate limit or outage")
            daily = conn.execute(
                "SELECT COUNT(*),COALESCE(SUM(billed_seconds),0) FROM groq_requests WHERE day=?",
                (day,),
            ).fetchone()
            hourly = conn.execute(
                "SELECT COALESCE(SUM(billed_seconds),0) FROM groq_requests WHERE timestamp>?",
                (now - 3600,),
            ).fetchone()[0]
            minute = conn.execute(
                "SELECT COUNT(*) FROM groq_requests WHERE timestamp>?", (now - 60,)
            ).fetchone()[0]
            if (
                daily[0] + 1 > caps.daily_requests * caps.budget_fraction
                or daily[1] + billed > caps.daily_seconds * caps.budget_fraction
                or hourly + billed > caps.hourly_seconds * caps.budget_fraction
            ):
                raise GroqUnavailableError("Groq safety budget reached")
            if minute + 1 > caps.requests_per_minute * caps.budget_fraction:
                oldest = conn.execute("SELECT MIN(timestamp) FROM groq_requests WHERE timestamp>?", (now-60,)).fetchone()[0]
                raise GroqDeferredError("Groq request pacing", max(1, 61-(now-oldest)))
            return conn.execute(
                """INSERT INTO groq_requests
                (timestamp,day,audio_seconds,billed_seconds,status) VALUES (?,?,?,?,?)""",
                (now, day, seconds, billed, "reserved"),
            ).lastrowid

    def transcribe(self, audio, sample_rate, language=None):
        key = os.environ.get("GROQ_API_KEY", "")
        if not key:
            raise GroqUnavailableError("Groq key is not configured")
        pcm = (np.clip(audio.reshape(-1), -1, 1) * 32767).astype("<i2")
        blob = io.BytesIO()
        with wave.open(blob, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm.tobytes())
        if blob.tell() >= 20 * 1024 * 1024:
            raise GroqUnavailableError("Upload unit exceeds the safe size limit")
        request_id = self.reserve(len(pcm) / sample_rate)
        data = [
            ("model", self.config.transcription.groq_model),
            ("response_format", "verbose_json"),
            ("timestamp_granularities[]", "word"),
            ("timestamp_granularities[]", "segment"),
            ("temperature", "0"),
        ]
        if language or self.config.asr.language:
            data.append(("language", language or self.config.asr.language))

        try:
            response = self.session.post(
                self.endpoint,
                headers={"Authorization": "Bearer " + key, "User-Agent": "voice-journal/2.1"},
                data=data,
                files={"file": ("speech.wav", blob.getvalue(), "audio/wav")},
                timeout=(5, 25),
            )
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower().startswith("x-ratelimit") or k.lower() == "retry-after"
            }
            with self.store.connect() as conn:
                conn.execute(
                    "UPDATE groq_requests SET status=?,headers=? WHERE id=?",
                    (str(response.status_code), json.dumps(headers), request_id),
                )
                if response.status_code >= 400:
                    try:
                        delay = max(5, min(86400, float(response.headers.get("retry-after", 30))))
                    except ValueError:
                        delay = 60
                    if response.status_code in (401, 403):
                        delay = 300
                    conn.execute(
                        "INSERT OR REPLACE INTO service_state VALUES (?,?)",
                        ("groq_retry_at", str(time.time() + delay)),
                    )
            if response.status_code != 200:
                raise GroqUnavailableError(f"Groq HTTP {response.status_code}")
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                raise GroqUnavailableError("Groq returned an invalid transcription response")
            return payload
        except (requests.RequestException, ValueError):
            with self.store.connect() as conn:
                conn.execute(
                    "UPDATE groq_requests SET status=? WHERE id=?",
                    ("network_or_decode_error", request_id),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO service_state VALUES (?,?)",
                    ("groq_retry_at", str(time.time() + 30)),
                )
            raise GroqUnavailableError("Groq is unreachable or returned invalid JSON") from None
