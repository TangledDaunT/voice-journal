"""Basic unit tests for voice journal package."""

import pytest
from voice_journal.config.settings import Config


class TestConfig:
    """Test configuration loading."""

    def test_default_config(self):
        """Test default configuration creation."""
        config = Config()
        assert config.audio.sample_rate == 16000
        assert config.asr.model_size == "small"
        assert config.conversation.gap_seconds == 90.0

    def test_vad_threshold_bounds(self):
        """Test VAD threshold is between 0 and 1."""
        config = Config()
        assert 0.0 <= config.vad.threshold <= 1.0


class TestPipeline:
    """Test pipeline components."""

    def test_imports(self):
        """Test all modules can be imported."""
        from voice_journal.audio_capture import AudioCapture
        from voice_journal.vad import VADProcessor
        from voice_journal.speaker_id import SpeakerIdentifier
        from voice_journal.asr import ASRProcessor
        from voice_journal.conversation import ConversationGrouper
        from voice_journal.llm_output import LLMClassifier
        from voice_journal.obsidian import ObsidianWriter
        from voice_journal.storage import SQLiteStore

        assert AudioCapture is not None
        assert VADProcessor is not None
        assert SpeakerIdentifier is not None
        assert ASRProcessor is not None
        assert ConversationGrouper is not None
        assert LLMClassifier is not None
        assert ObsidianWriter is not None
        assert SQLiteStore is not None
