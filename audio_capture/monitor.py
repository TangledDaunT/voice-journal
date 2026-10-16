"""Short, expiring PCM buffer for explicit dashboard listening, outside callbacks."""

import io
import wave

import numpy as np

from audio_capture.monitor_buffer import MonitorBuffer


class MicrophoneMonitor:
    def __init__(self, config):
        self.buffer = MonitorBuffer(config, reset=True)
        self.parts = []
        self.samples = 0

    @property
    def active(self):
        return self.buffer.active

    def cleanup(self):
        self.buffer.clear_expired()

    def feed(self, chunk):
        if not self.active:
            self.parts = []
            self.samples = 0
            self.cleanup()
            return
        self.parts.append(chunk.audio)
        self.samples += len(chunk.audio)
        if self.samples < chunk.sample_rate * 0.25:
            return
        pcm = (np.clip(np.concatenate(self.parts).reshape(-1), -1, 1) * 32767).astype("<i2")
        blob = io.BytesIO()
        with wave.open(blob, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(chunk.sample_rate)
            wav.writeframes(pcm.tobytes())
        self.buffer.publish(blob.getvalue())
        self.parts = []
        self.samples = 0
