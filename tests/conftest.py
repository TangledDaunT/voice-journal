"""Pytest fixtures for common test patterns."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

from config.settings import Config
from vad.silero_vad import SpeechSegment


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_config(temp_dir):
    """Create a config with temporary paths."""
    config = Config()
    config.database.path = str(temp_dir / "test.db")
    config.audio.audio_storage_path = str(temp_dir / "audio")
    config.obsidian.vault_path = str(temp_dir / "vault")
    return config


@pytest.fixture
def sample_audio():
    """Generate sample audio data (1 second)."""
    sample_rate = 16000
    duration = 1.0
    samples = int(duration * sample_rate)
    audio = np.random.randn(samples).astype(np.float32) * 0.1
    return audio, sample_rate


@pytest.fixture
def speech_segment(sample_audio):
    """Create a test speech segment."""
    audio, sample_rate = sample_audio
    now = datetime.now()

    return SpeechSegment(
        start_time=now,
        end_time=now + timedelta(seconds=1.0),
        audio=audio,
        sample_rate=sample_rate
    )


@pytest.fixture
def batch_speech_segments():
    """Create multiple test speech segments."""
    sample_rate = 16000
    now = datetime.now()
    segments = []

    for i in range(5):
        duration = 2.0
        samples = int(duration * sample_rate)
        audio = np.random.randn(samples).astype(np.float32) * 0.1

        seg = SpeechSegment(
            start_time=now + timedelta(seconds=i * 3),  # 3s apart
            end_time=now + timedelta(seconds=i * 3 + duration),
            audio=audio,
            sample_rate=sample_rate
        )
        segments.append(seg)

    return segments
