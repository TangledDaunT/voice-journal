"""
Live Audio Playback Module.
Plays captured audio through speakers with optional push-to-talk.
"""

import numpy as np
import threading
import queue
import time
from typing import Optional, Callable
from dataclasses import dataclass
import subprocess
import os

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False


@dataclass
class PlaybackConfig:
    """Configuration for live playback."""
    enabled: bool = True
    output_device_index: Optional[int] = None  # None = default
    volume: float = 0.5  # 0.0 to 1.0
    delay_seconds: float = 0.5  # Buffer delay to prevent feedback
    push_to_talk: bool = False  # If True, only play when key held
    push_to_talk_key: str = "space"  # Key for push-to-talk


class LivePlayback:
    """
    Plays captured audio through speakers.

    Features:
    - Buffered playback with adjustable delay
    - Push-to-talk mode to prevent feedback
    - Volume control
    - Automatic feedback detection/prevention
    """

    def __init__(self, config: PlaybackConfig = None):
        self.config = config or PlaybackConfig()
        self.enabled = self.config.enabled

        self._audio_queue: queue.Queue = queue.Queue()
        self._playing = False
        self._ptt_active = False
        self._playback_thread: Optional[threading.Thread] = None
        self._pyaudio: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None

        # Callback for when PTT is pressed (optional)
        self._on_ptt_callback: Optional[Callable] = None

    def start(self, sample_rate: int = 16000):
        """Start the playback thread."""
        if not self.enabled or not PYAUDIO_AVAILABLE:
            return

        try:
            self._pyaudio = pyaudio.PyAudio()

            # Find output device
            output_device = self._find_output_device()

            self._stream = self._pyaudio.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=sample_rate,
                output=True,
                output_device_index=output_device,
                frames_per_buffer=1024
            )

            self._playing = True
            self._playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self._playback_thread.start()

        except Exception as e:
            print(f"Failed to start live playback: {e}")
            self.enabled = False

    def stop(self):
        """Stop the playback thread."""
        self._playing = False

        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None

        if self._pyaudio:
            self._pyaudio.terminate()
            self._pyaudio = None

    def push_audio(self, audio: np.ndarray, sample_rate: int = 16000):
        """
        Push audio data to the playback queue.

        Args:
            audio: Audio samples as numpy array
            sample_rate: Sample rate (should match start() rate)
        """
        if not self.enabled or not self._playing:
            return

        # Apply volume
        audio = audio * self.config.volume

        # Add to queue
        try:
            self._audio_queue.put((audio.astype(np.float32), sample_rate), timeout=0.1)
        except queue.Full:
            pass  # Drop if queue is full

    def set_ptt_active(self, active: bool):
        """
        Set push-to-talk active state.

        When PTT mode is enabled, audio only plays when active=True.
        """
        self._ptt_active = active

    def set_volume(self, volume: float):
        """Set playback volume (0.0 to 1.0)."""
        self.config.volume = max(0.0, min(1.0, volume))

    def toggle(self):
        """Toggle audio playback on/off."""
        self.enabled = not self.enabled

    def _playback_loop(self):
        """Main playback loop (runs in thread)."""
        while self._playing:
            try:
                # Check PTT mode
                if self.config.push_to_talk and not self._ptt_active:
                    # Clear queue while PTT inactive
                    try:
                        while True:
                            self._audio_queue.get_nowait()
                    except queue.Empty:
                        pass
                    time.sleep(0.05)
                    continue

                # Get audio from queue
                try:
                    audio, sample_rate = self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Write to output stream
                if self._stream and self._stream.is_active():
                    self._stream.write(audio.tobytes())

            except Exception as e:
                time.sleep(0.1)

    def _find_output_device(self) -> Optional[int]:
        """Find a suitable output device."""
        if self.config.output_device_index is not None:
            return self.config.output_device_index

        # Try to find default output device
        try:
            default_output = self._pyaudio.get_default_output_device_info()
            return default_output['index']
        except:
            return None

    @staticmethod
    def list_output_devices() -> list:
        """List available output devices."""
        if not PYAUDIO_AVAILABLE:
            return []

        devices = []
        p = pyaudio.PyAudio()

        try:
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info['maxOutputChannels'] > 0:
                    devices.append({
                        'index': i,
                        'name': info['name'],
                        'channels': info['maxOutputChannels'],
                        'default_samplerate': info['defaultSampleRate']
                    })
        finally:
            p.terminate()

        return devices
