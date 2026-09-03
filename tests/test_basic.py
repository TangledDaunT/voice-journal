"""Basic unit tests for voice journal package."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from config.settings import Config


class TestConfig:
    """Test configuration loading."""

    def test_default_config(self):
        """Test default configuration creation."""
        config = Config()
        assert config.audio.sample_rate == 16000
        assert config.asr.model_size == "Hub84/faster-whisper-hinglish-prime"
        assert config.conversation.gap_seconds == 90.0

    def test_vad_threshold_bounds(self):
        """Test VAD threshold is between 0 and 1."""
        config = Config()
        assert 0.0 <= config.vad.threshold <= 1.0


class TestPipeline:
    """Test pipeline components."""

    def test_imports(self):
        """Test all modules can be imported."""
        from audio_capture.capture import AudioCapture
        from vad.silero_vad import VADProcessor
        from speaker_id.identification import SpeakerIdentifier
        from asr.transcriber import ASRProcessor
        from conversation.grouping import ConversationGrouper
        from llm_output.classifier import LLMClassifier
        from obsidian.output import ObsidianWriter
        from storage.database import SQLiteStore

        assert AudioCapture is not None
        assert VADProcessor is not None
        assert SpeakerIdentifier is not None
        assert ASRProcessor is not None
        assert ConversationGrouper is not None
        assert LLMClassifier is not None
        assert ObsidianWriter is not None
        assert SQLiteStore is not None
