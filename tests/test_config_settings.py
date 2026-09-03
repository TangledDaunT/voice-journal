"""Tests for confidence gating in ASR."""

import pytest
import numpy as np

from asr.transcriber_batch import BatchASRProcessor, ConfidenceMetrics, TranscriptSegmentWithConfidence
from datetime import datetime


class TestConfidenceMetrics:
    """Tests for ConfidenceMetrics."""

    def test_is_low_confidence_high_no_speech(self):
        """Test low confidence detection from no_speech_prob."""
        metrics = ConfidenceMetrics(no_speech_prob=0.7, avg_logprob=-0.5)

        assert metrics.is_low_confidence == True

    def test_is_low_confidence_low_logprob(self):
        """Test low confidence detection from avg_logprob."""
        metrics = ConfidenceMetrics(no_speech_prob=0.2, avg_logprob=-1.5)

        assert metrics.is_low_confidence == True

    def test_is_high_confidence(self):
        """Test high confidence detection."""
        metrics = ConfidenceMetrics(no_speech_prob=0.1, avg_logprob=-0.3)

        assert metrics.is_low_confidence == False


class TestTranscriptSegmentWithConfidence:
    """Tests for TranscriptSegmentWithConfidence."""

    def test_format_for_obsidian_high_confidence(self):
        """Test formatting without confidence marker."""
        segment = TranscriptSegmentWithConfidence(
            text="Hello world",
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=5.0,
            language="en",
            language_probability=0.9,
            speaker="shreyansh",
            speaker_confidence=0.8,
            words=[],
            confidence_metrics=ConfidenceMetrics(no_speech_prob=0.1, avg_logprob=-0.3),
            low_confidence=False
        )

        formatted = segment.format_for_obsidian()

        assert "⚠️" not in formatted

    def test_format_for_obsidian_low_confidence(self):
        """Test formatting with confidence marker."""
        segment = TranscriptSegmentWithConfidence(
            text="Hello world",
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=5.0,
            language="en",
            language_probability=0.5,
            speaker="unknown",
            speaker_confidence=0.3,
            words=[],
            confidence_metrics=ConfidenceMetrics(no_speech_prob=0.7, avg_logprob=-1.5),
            low_confidence=True
        )

        formatted = segment.format_for_obsidian()

        assert "⚠️" in formatted

    def test_format_for_obsidian_repetition_detected(self):
        segment = TranscriptSegmentWithConfidence(
            text="बच्च्च्च्च्च्च्च्च्च्च्च्च्च्च्च्च्च्च",
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=5.0,
            language="hi",
            language_probability=0.9,
            speaker="unknown",
            speaker_confidence=0.0,
            repetition_detected=True,
        )

        assert "repetition-detected" in segment.format_for_obsidian()


class TestBatchASRProcessor:
    """Tests for BatchASRProcessor."""

    def test_similarity_to_confidence(self):
        """Test similarity to confidence conversion."""
        from config.settings import Config

        config = Config()
        config.asr.model_size = "large-v3"
        config.asr.compute_type = "int8"

        # Skip if faster-whisper not available
        try:
            processor = BatchASRProcessor(config)
        except ImportError:
            pytest.skip("faster-whisper not installed")

        # At threshold (0.75) should return ~0.5
        conf = processor._similarity_to_confidence(0.75)
        assert conf == pytest.approx(0.5, abs=0.1)

        # At 1.0 should return 1.0
        conf = processor._similarity_to_confidence(1.0)
        assert conf == pytest.approx(1.0, abs=0.1)

    def test_repetition_loop_detection(self):
        repeated = "अब " * 80
        normal = "अब हम इस बातचीत के अगले हिस्से पर चलते हैं और फिर वापस आते हैं"

        assert BatchASRProcessor._has_repetition_loop(repeated)
        assert not BatchASRProcessor._has_repetition_loop(normal)

    def test_correct_language_hindi_to_russian(self):
        """Test Hindi misidentified as Russian correction."""
        from config.settings import Config

        config = Config()
        config.asr.model_size = "large-v3"

        try:
            processor = BatchASRProcessor(config)
        except ImportError:
            pytest.skip("faster-whisper not installed")

        # Text with Hindi words but detected as Russian
        text = "yeh kaam hai kya"  # Hindi words in Latin script
        detected = "ru"

        corrected = processor._correct_language(text, detected)

        # Should be corrected to Hindi (has Hindi words but no Cyrillic)
        assert corrected == "hi"

    def test_correct_language_preserves_correct_detection(self):
        """Test that correct language detection is preserved."""
        from config.settings import Config

        config = Config()
        config.asr.model_size = "large-v3"

        try:
            processor = BatchASRProcessor(config)
        except ImportError:
            pytest.skip("faster-whisper not installed")

        text = "Hello world this is English"
        detected = "en"

        corrected = processor._correct_language(text, detected)

        # Should remain English
        assert corrected == "en"
