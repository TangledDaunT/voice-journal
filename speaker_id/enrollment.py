"""Use the daemon's exact microphone stream for 30-second enrollment, never browser audio."""

import json
import time
from pathlib import Path

import numpy as np

from utils.data_lock import data_lock, write_json

ACTIVE = {"queued", "recording", "analyzing"}


class EnrollmentRecorder:
    def __init__(self, config, storage_guard=None):
        self.config = config
        self.storage_guard = storage_guard
        self.root = Path(config.database.path).parent.parent
        self.request_path = self.root / "runtime/enrollment_request.json"
        self.state_path = self.root / "runtime/enrollment.json"
        self.current = None
        self.chunks = []
        self.samples = 0
        self.active = False
        self.last_update = 0

    def state(self):
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def tick(self):
        if self.storage_guard:
            self.storage_guard(self.config)
        try:
            request = json.loads(self.request_path.read_text())
        except (OSError, ValueError):
            self.active = False
            self.current = None
            self.chunks = []
            self.samples = 0
            return
        state = self.state()
        if request.get("cancel"):
            if state.get("status") in ACTIVE:
                write_json(self.state_path, dict(state, status="cancelled"))
            self.active = False
            self.chunks = []
            self.samples = 0
            return
        if state.get("id") == request["id"] and state.get("status") in {
            "complete",
            "error",
            "cancelled",
            "analyzing",
        }:
            self.active = False
            return
        if self.current is None or self.current["id"] != request["id"]:
            # A process restart must not silently enroll an incomplete old sample.
            if state.get("id") == request["id"] and state.get("status") == "recording":
                write_json(
                    self.state_path,
                    dict(state, status="error", error="Recording was interrupted; please retry."),
                )
                return
            self.current = request
            self.chunks = []
            self.samples = 0
            self.active = True
            self.started = time.monotonic()
        if self.active and time.monotonic() - self.started > 42:
            write_json(
                self.state_path,
                dict(
                    request,
                    status="error",
                    error="Microphone did not deliver 30 seconds of audio. Check the input and retry.",
                ),
            )
            self.active = False
            self.chunks = []

    def feed(self, audio):
        if not self.active or self.current is None:
            return False
        if self.storage_guard:
            self.storage_guard(self.config)
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        take = min(len(audio), 30 * 16000 - self.samples)
        if take > 0:
            self.chunks.append(audio[:take].copy())
            self.samples += take
        now = time.monotonic()
        if now - self.last_update > 0.5:
            write_json(
                self.state_path,
                dict(
                    self.current,
                    status="recording",
                    seconds_recorded=self.samples / 16000,
                    input_rms_db=round(
                        20 * np.log10(max(float(np.sqrt(np.mean(audio**2))), 1e-10)), 1
                    ),
                ),
            )
            self.last_update = now
        if self.samples == 30 * 16000:
            with data_lock(self.config):
                if not self.request_path.exists():
                    self.active = False
                    self.chunks = []
                    return True
                latest = json.loads(self.request_path.read_text())
                if latest.get("cancel") or latest["id"] != self.current["id"]:
                    self.active = False
                    self.chunks = []
                    return True
                from scipy.io.wavfile import write

                directory = self.root / "calibration/enrollments"
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / (self.current["id"] + ".wav")
                write(
                    str(path),
                    16000,
                    (np.clip(np.concatenate(self.chunks), -1, 1) * 32767).astype(np.int16),
                )
                write_json(
                    self.state_path,
                    dict(
                        self.current, status="analyzing", seconds_recorded=30, audio_path=str(path)
                    ),
                )
            self.active = False
            self.chunks = []
        return True
