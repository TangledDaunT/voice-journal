"""
Stage 1: Continuous Audio Capture.
Captures microphone input into a ring buffer, resilient to disconnects.
"""

import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path
import numpy as np
import sounddevice as sd
from ..config.settings import Config
from ..utils.logger import logger, log_stage


@dataclass
class AudioChunk:
    """Container for an audio chunk with metadata."""
    audio: np.ndarray  # Shape: (samples, channels), dtype: float32
    sample_rate: int
    timestamp: datetime
    duration: float  # seconds

    @property
    def samples(self) -> int:
        return self.audio.shape[0]

    @property
    def duration_ms(self) -> int:
        return int(self.duration * 1000)


class RingBuffer:
    """
    Thread-safe ring buffer for continuous audio storage.
    Stores up to `max_seconds` of audio at the given sample rate.
    """

    def __init__(self, sample_rate: int, max_seconds: int, channels: int = 1):
        self.sample_rate = sample_rate
        self.max_seconds = max_seconds
        self.channels = channels
        self.max_samples = sample_rate * max_seconds

        # Pre-allocate buffer
        self.buffer = np.zeros((self.max_samples, channels), dtype=np.float32)
        self.write_idx = 0
        self.lock = threading.Lock()
        self.total_written = 0

    def write(self, audio: np.ndarray):
        """Write audio samples to the ring buffer."""
        if audio.ndim == 1:
            audio = audio.reshape(-1, 1)

        n_samples = audio.shape[0]

        with self.lock:
            # Handle wraparound
            end_idx = self.write_idx + n_samples
            if end_idx <= self.max_samples:
                self.buffer[self.write_idx:end_idx] = audio
            else:
                # Wrap around
                first_part = self.max_samples - self.write_idx
                self.buffer[self.write_idx:] = audio[:first_part]
                self.buffer[:n_samples - first_part] = audio[first_part:]

            self.write_idx = (self.write_idx + n_samples) % self.max_samples
            self.total_written += n_samples

    def read_last(self, seconds: float) -> np.ndarray:
        """Read the last `seconds` of audio from the buffer."""
        n_samples = int(seconds * self.sample_rate)
        n_samples = min(n_samples, self.total_written)

        with self.lock:
            if self.total_written < self.max_samples:
                # Buffer not yet full
                start_idx = max(0, self.write_idx - n_samples)
                return self.buffer[start_idx:self.write_idx].copy()
            else:
                # Buffer is full, handle wraparound
                start_idx = (self.write_idx - n_samples) % self.max_samples
                if start_idx < self.write_idx:
                    return self.buffer[start_idx:self.write_idx].copy()
                else:
                    # Wrap around
                    return np.concatenate([
                        self.buffer[start_idx:],
                        self.buffer[:self.write_idx]
                    ])

    def read_range(self, start_seconds: float, duration_seconds: float) -> np.ndarray:
        """Read a specific time range from the buffer."""
        n_samples = int(duration_seconds * self.sample_rate)
        start_sample = int(start_seconds * self.sample_rate)
        start_sample = start_sample % self.max_samples

        with self.lock:
            end_sample = (start_sample + n_samples) % self.max_samples
            if start_sample < end_sample:
                return self.buffer[start_sample:end_sample].copy()
            else:
                return np.concatenate([
                    self.buffer[start_sample:],
                    self.buffer[:end_sample]
                ])

    def clear(self):
        """Clear the buffer."""
        with self.lock:
            self.buffer.fill(0)
            self.write_idx = 0
            self.total_written = 0


class AudioCapture:
    """
    Stage 1: Continuous audio capture from microphone.
    Runs indefinitely, resilient to disconnects/reconnects.
    """

    def __init__(
        self,
        config: Config,
        on_chunk: Optional[Callable[[AudioChunk], None]] = None
    ):
        self.config = config
        self.on_chunk = on_chunk

        self.sample_rate = config.audio.sample_rate
        self.channels = config.audio.channels
        self.block_size = config.audio.block_size
        self.ring_buffer = RingBuffer(
            sample_rate=self.sample_rate,
            max_seconds=config.audio.ring_buffer_seconds,
            channels=self.channels
        )

        self.is_running = False
        self.is_muted = False
        self.stream: Optional[sd.InputStream] = None
        self.mute_file = Path(config.daemon.mute_file)

        # Create mute file directory
        self.mute_file.parent.mkdir(parents=True, exist_ok=True)

        # Queue for communication with callback
        self.chunk_queue: queue.Queue[AudioChunk | None] = queue.Queue()

        logger.info(f"AudioCapture initialized: {self.sample_rate}Hz, {self.channels}ch")

    def _audio_callback(self, indata: np.ndarray, frames: int,
                        time_info: dict, status: sd.CallbackFlags):
        """Callback for sounddevice stream."""
        if status:
            logger.warning(f"Audio callback status: {status}")

        # Check mute flag
        if self.is_muted or self.mute_file.exists():
            return  # Skip recording

        # Write to ring buffer
        self.ring_buffer.write(indata.copy())

        # Create chunk and queue it
        chunk = AudioChunk(
            audio=indata.copy(),
            sample_rate=self.sample_rate,
            timestamp=datetime.now(),
            duration=frames / self.sample_rate
        )
        self.chunk_queue.put(chunk)

    def _process_chunks(self):
        """Process chunks from the queue in a separate thread."""
        while self.is_running:
            try:
                chunk = self.chunk_queue.get(timeout=0.1)
                if chunk is None:
                    break
                if self.on_chunk:
                    self.on_chunk(chunk)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing audio chunk: {e}")

    def start(self):
        """Start capturing audio continuously."""
        if self.is_running:
            logger.warning("AudioCapture already running")
            return

        self.is_running = True

        # Start chunk processing thread
        self.process_thread = threading.Thread(target=self._process_chunks, daemon=True)
        self.process_thread.start()

        # Start audio stream with resilience
        self._start_stream()

        logger.info("AudioCapture started")

    def _start_stream(self):
        """Start the audio stream with error handling."""
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.block_size,
                callback=self._audio_callback,
                dtype=np.float32
            )
            self.stream.start()
            log_stage("AudioCapture", f"Stream started: {self.sample_rate}Hz")
        except sd.PortAudioError as e:
            logger.error(f"Failed to start audio stream: {e}")
            logger.info("Attempting to reconnect in 5 seconds...")
            if self.is_running:
                threading.Timer(5.0, self._start_stream).start()

    def stop(self):
        """Stop capturing audio."""
        self.is_running = False

        # Signal chunk processor to stop
        self.chunk_queue.put(None)

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        logger.info("AudioCapture stopped")

    def mute(self):
        """Mute audio capture (stop recording)."""
        self.is_muted = True
        self.mute_file.touch()
        logger.info("🔇 Audio muted")
        return True

    def unmute(self):
        """Unmute audio capture (resume recording)."""
        self.is_muted = False
        if self.mute_file.exists():
            self.mute_file.unlink()
        logger.info("🔊 Audio unmuted")
        return True

    def toggle_mute(self) -> bool:
        """Toggle mute state. Returns new state (True=muted)."""
        if self.is_muted:
            self.unmute()
            return False
        else:
            self.mute()
            return True

    def get_mute_status(self) -> bool:
        """Check if currently muted."""
        return self.is_muted or self.mute_file.exists()

    def get_recent_audio(self, seconds: float) -> AudioChunk:
        """Get the last N seconds of audio from the buffer."""
        audio = self.ring_buffer.read_last(seconds)
        return AudioChunk(
            audio=audio,
            sample_rate=self.sample_rate,
            timestamp=datetime.now(),
            duration=seconds
        )


def list_audio_devices():
    """List all available audio input devices."""
    devices = sd.query_devices()
    input_devices = []

    for idx, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            input_devices.append({
                'index': idx,
                'name': dev['name'],
                'channels': dev['max_input_channels'],
                'sample_rate': dev['default_samplerate']
            })

    return input_devices


if __name__ == "__main__":
    # Quick test
    import time

    config = Config()
    capture = AudioCapture(config)

    print("Starting capture for 5 seconds...")
    capture.start()

    for i in range(5):
        time.sleep(1)
        print(f"Captured... {i+1}/5")

    capture.stop()
    print("Stopped")
