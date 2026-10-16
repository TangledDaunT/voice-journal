"""Conservative enrolled-speaker verification; never use pitch or MFCC fallbacks."""

import json
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

MODEL_ID = "resemblyzer-0.1.4-256d"
SCHEMA = """
CREATE TABLE IF NOT EXISTS speaker_profiles (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, canonical_name TEXT UNIQUE NOT NULL,
 embeddings TEXT NOT NULL, model TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
 recorded_seconds REAL NOT NULL, voiced_seconds REAL NOT NULL,
 quality_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS speaker_filter_decisions (
 source_id TEXT PRIMARY KEY, status TEXT NOT NULL, audio_path TEXT NOT NULL,
 details_json TEXT NOT NULL, processed_at TEXT NOT NULL
);
"""


class SpeakerModelUnavailableError(RuntimeError):
    pass


@dataclass
class SpeakerSpan:
    start: int
    end: int
    speaker_id: str
    name: str
    similarity: float


class VoiceEncoder:
    """One CPU encoder per worker, with bundled weights and no network download."""

    def __init__(self):
        self.encoder = None

    def embed(self, audio, sample_rate=16000):
        if sample_rate != 16000:
            raise ValueError("Speaker verification requires 16 kHz audio")
        if self.encoder is None:
            try:
                import torch
                from resemblyzer import VoiceEncoder as ResemblyzerEncoder

                torch.set_num_threads(1)
                self.encoder = ResemblyzerEncoder(device="cpu", verbose=False)
            except Exception as exc:
                raise SpeakerModelUnavailableError(
                    "Speaker encoder unavailable; transcription is blocked"
                ) from exc
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if len(audio) < 16000:
            raise ValueError("Too little speech for a reliable speaker embedding")
        result = self.encoder.embed_utterance(audio)
        norm = float(np.linalg.norm(result))
        if norm < 1e-8 or not np.isfinite(result).all():
            raise ValueError("Invalid speaker embedding")
        return result.astype(np.float32) / norm


def speech_samples(audio, sample_rate=16000):
    """Remove non-speech frames for enrollment/embedding only; never alter time maps."""
    import webrtcvad

    detector = webrtcvad.Vad(2)
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    frame_samples = sample_rate * 30 // 1000
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    flags = []
    for start in range(0, len(audio) - frame_samples + 1, frame_samples):
        part = pcm[start : start + frame_samples]
        voiced = detector.is_speech(part.tobytes(), sample_rate)
        energy = float(np.sqrt(np.mean(audio[start : start + frame_samples] ** 2)))
        flags.append((start, voiced and energy > 0.001))
    selected = [audio[start : start + frame_samples] for start, voiced in flags if voiced]
    return np.concatenate(selected) if selected else np.empty(0, dtype=np.float32)


class VoiceGate:
    def __init__(self, config, store, encoder=None):
        self.config = config
        self.store = store
        self.encoder = encoder or VoiceEncoder()
        self.enrollment_detector = None
        with store.connect() as conn:
            conn.executescript(SCHEMA)

    def profiles(self, enabled_only=False):
        with self.store.connect() as conn:
            return conn.execute(
                "SELECT * FROM speaker_profiles"
                + (" WHERE enabled=1" if enabled_only else "")
                + " ORDER BY name"
            ).fetchall()

    @staticmethod
    def score(embedding, profiles, threshold, margin):
        scores = []
        for profile in profiles:
            references = np.asarray(json.loads(profile["embeddings"]), dtype=np.float32)
            similarities = references @ embedding
            scores.append((float(np.max(similarities)), profile))
        scores.sort(key=lambda item: item[0], reverse=True)
        if not scores:
            return None, "no_enrolled_speakers", 0.0
        best, profile = scores[0]
        if best < threshold:
            return None, "unknown_or_media", best
        if len(scores) > 1 and best - scores[1][0] < margin:
            return None, "ambiguous_or_overlap", best
        return profile, "matched", best

    def classify(self, audio, sample_rate=16000):
        profiles = [p for p in self.profiles(True) if p["model"] == MODEL_ID]
        if not profiles:
            return [], {"reason": "no_enrolled_speakers", "accepted_seconds": 0}
        config = self.config.speaker
        hop = sample_rate
        window = sample_rate * 2
        if len(audio) < window:
            return [], {"reason": "too_short_for_verification", "accepted_seconds": 0}
        # Overlapping context windows must agree before a one-second core is admitted.
        windows = []
        starts = list(range(0, len(audio) - window + 1, hop))
        if starts[-1] + window < len(audio):
            starts.append(len(audio) - window)
        reasons = {}
        for start in starts:
            samples = speech_samples(audio[start : start + window], sample_rate)
            if len(samples) < sample_rate:
                match, reason, similarity = None, "insufficient_speech", 0.0
            else:
                embedding = self.encoder.embed(samples, sample_rate)
                match, reason, similarity = self.score(
                    embedding, profiles, config.similarity_threshold, config.similarity_margin
                )
            reasons[reason] = reasons.get(reason, 0) + 1
            windows.append((start, start + window, match, similarity))
        spans = []
        for start in range(0, len(audio), hop):
            end = min(start + hop, len(audio))
            covering = [w for w in windows if w[0] < end and w[1] > start]
            if not covering or any(w[2] is None for w in covering):
                continue
            ids = {w[2]["id"] for w in covering}
            if len(ids) != 1:
                continue
            profile = covering[0][2]
            similarity = min(w[3] for w in covering)
            if spans and spans[-1].end == start and spans[-1].speaker_id == profile["id"]:
                spans[-1].end = end
                spans[-1].similarity = min(spans[-1].similarity, similarity)
            else:
                spans.append(SpeakerSpan(start, end, profile["id"], profile["name"], similarity))
        spans = [s for s in spans if (s.end - s.start) / sample_rate >= config.min_matched_seconds]
        return spans, {
            "reason": "matched" if spans else "unknown_media_or_ambiguous",
            "window_reasons": reasons,
            "accepted_seconds": sum(s.end - s.start for s in spans) / sample_rate,
            "source_seconds": len(audio) / sample_rate,
        }

    def enroll(self, name, audio, profile_id):
        if not 29.9 <= len(audio) / 16000 <= 30.1:
            raise ValueError("Enrollment must contain 30 seconds of captured audio")
        clipping = float(np.mean(np.abs(audio) >= 0.99))
        if clipping > 0.03:
            raise ValueError("Recording is clipping. Reduce microphone gain and retry.")
        references = []
        voiced_total = 0.0
        all_vectors = []
        # Separate near/middle/far prototypes rather than averaging away room positions.
        for offset in range(0, 30 * 16000, 10 * 16000):
            raw = audio[offset : offset + 10 * 16000]
            if self.enrollment_detector is not None:
                spans = self.enrollment_detector(raw)
                parts = [raw[start:end] for start, end, *_ in spans]
                block = np.concatenate(parts) if parts else np.empty(0, dtype=np.float32)
            else:
                block = speech_samples(raw)
            voiced_total += len(block) / 16000
            vectors = []
            for start in range(0, len(block) - 2 * 16000 + 1, 2 * 16000):
                vector = self.encoder.embed(block[start : start + 2 * 16000])
                vectors.append(vector)
                all_vectors.append(vector)
            if vectors:
                mean = np.mean(vectors, axis=0)
                mean /= np.linalg.norm(mean)
                references.append(mean)
        if voiced_total < 10 or len(all_vectors) < 5 or len(references) < 2:
            raise ValueError(
                "Not enough clear speech across the recording. Speak for most of the 30 seconds and retry with media paused."
            )
        # Reject clearly inconsistent enrollments, but do not call this an accuracy measurement.
        centre = np.mean(all_vectors, axis=0)
        centre /= np.linalg.norm(centre)
        consistency = float(np.median(np.asarray(all_vectors) @ centre))
        if consistency < 0.70:
            raise ValueError(
                "Voice sample is inconsistent. One person should speak, with other voices and media off."
            )
        quality = {
            "voiced_seconds": round(voiced_total, 2),
            "prototype_count": len(references),
            "window_count": len(all_vectors),
            "self_consistency": round(consistency, 4),
            "clipping_fraction": round(clipping, 5),
            "accuracy_verified": False,
        }
        stamp = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
        with self.store.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM speaker_profiles WHERE canonical_name=?", (name.casefold(),)
            ).fetchone()
            if existing:
                profile_id = existing["id"]
            conn.execute(
                """INSERT INTO speaker_profiles
                (id,name,canonical_name,embeddings,model,enabled,recorded_seconds,voiced_seconds,quality_json,updated_at)
                VALUES (?,?,?,?,?,1,30,?,?,?) ON CONFLICT(canonical_name) DO UPDATE SET
                name=excluded.name,embeddings=excluded.embeddings,model=excluded.model,enabled=1,
                recorded_seconds=30,voiced_seconds=excluded.voiced_seconds,quality_json=excluded.quality_json,updated_at=excluded.updated_at""",
                (
                    profile_id,
                    name,
                    name.casefold(),
                    json.dumps([r.tolist() for r in references]),
                    MODEL_ID,
                    voiced_total,
                    json.dumps(quality),
                    stamp,
                ),
            )
        return {"id": profile_id, "name": name, "quality": quality}
