"""Bounded speech units: retain pauses and flush on silence or a safe maximum."""

from datetime import timedelta

import numpy as np

from vad.silero_vad import SpeechSegment


class ContinuousSpeech:
    def __init__(self, detector, sample_rate=16000, target_seconds=12, max_seconds=24):
        self.detector = detector
        self.sample_rate = sample_rate
        self.target = target_seconds
        self.maximum = max_seconds
        self.audio = np.empty(0, dtype=np.float32)
        self.start = None
        self.core_start = 0

    def reset(self):
        self.audio = np.empty(0, dtype=np.float32)
        self.start = None
        self.core_start = 0

    def feed(self, audio, start, flush=False):
        audio = np.asarray(audio).reshape(-1)
        emitted = []
        if self.start is not None:
            expected = self.start + timedelta(seconds=len(self.audio) / self.sample_rate)
            if abs((start - expected).total_seconds()) > 0.025:
                emitted += self._emit(len(self.audio))
        if self.start is None:
            self.start = start
        self.audio = np.concatenate([self.audio, audio])
        duration = len(self.audio) / self.sample_rate
        if duration < self.target and not flush:
            return emitted
        spans = self.detector(self.audio)
        if not spans:
            self.reset()
            return emitted
        # Prefer a real pause near the target. Adjacent samples belong to only one unit.
        if duration >= self.maximum:
            # Lowest-energy 40ms frame in the last two seconds reduces mid-word cuts.
            limit = int(self.maximum * self.sample_rate)
            hop = int(0.04 * self.sample_rate)
            choices = range(limit - 2 * self.sample_rate, limit - self.sample_rate // 2, hop)
            cut = min(choices, key=lambda i: float(np.mean(self.audio[i : i + hop] ** 2)))
            emitted += self._emit(cut + hop // 2, context=True)
            if flush and len(self.audio) > self.core_start:
                expected = self.start + timedelta(seconds=len(self.audio) / self.sample_rate)
                emitted += self.feed(np.empty(0), expected, flush=True)
        elif flush or duration - spans[-1][1] / self.sample_rate >= 0.6:
            emitted += self._emit(len(self.audio))
        return emitted

    def _emit(self, samples, context=False):
        if not samples:
            return []
        overlap = self.sample_rate // 2 if context else 0
        available = min(len(self.audio), samples + overlap)
        end = self.start + timedelta(seconds=available / self.sample_rate)
        segment = SpeechSegment(
            self.start,
            end,
            self.audio[:available].copy(),
            self.sample_rate,
            core_start_samples=self.core_start,
            core_end_samples=samples,
        )
        retained = samples - overlap
        self.audio = self.audio[retained:]
        self.start = (
            self.start + timedelta(seconds=retained / self.sample_rate) if len(self.audio) else None
        )
        self.core_start = overlap
        return [segment]
