"""Tests for edge cases in the batch pipeline."""

import pytest
import numpy as np
from datetime import datetime, timedelta

from vad.segment_merger import SegmentMerger
from vad.silero_vad import SpeechSegment
from config.settings import Config


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_merge_empty_segments(self):
        """Test merging with no segments."""
        config = Config()
        merger = SegmentMerger(config)

        merged = merger.add_segments_batch([])

        assert merged == []

    def test_very_short_segment(self):
        """Test handling of segment shorter than minimum."""
        config = Config()
        config.segment_merging.min_transcription_unit_seconds = 5.0
        merger = SegmentMerger(config)

        sample_rate = 16000
        now = datetime.now()

        # 1 second segment (below minimum)
        seg = SpeechSegment(
            start_time=now,
            end_time=now + timedelta(seconds=1),
            audio=np.random.randn(1 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        merged = merger.add_segments_batch([seg])

        # Should still return something (policy: keep, don't discard)
        assert len(merged) == 1
        assert merged[0].duration_seconds < 5.0

    def test_very_long_segment_splitting(self):
        """Test splitting of very long segments."""
        config = Config()
        config.segment_merging.max_transcription_unit_seconds = 30.0
        merger = SegmentMerger(config)

        sample_rate = 16000
        now = datetime.now()

        # 60 second segment
        seg = SpeechSegment(
            start_time=now,
            end_time=now + timedelta(seconds=60),
            audio=np.random.randn(60 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        merged = merger.add_segments_batch([seg])

        # Should be split
        assert len(merged) >= 2
        for unit in merged:
            assert unit.duration_seconds <= 30.5  # Allow small buffer

    def test_segments_exactly_at_gap_threshold(self):
        """Test behavior when gap exactly equals threshold."""
        config = Config()
        config.segment_merging.merge_gap_seconds = 2.5
        merger = SegmentMerger(config)

        sample_rate = 16000
        now = datetime.now()

        seg1 = SpeechSegment(
            start_time=now,
            end_time=now + timedelta(seconds=5),
            audio=np.random.randn(5 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        # Gap exactly 2.5s
        seg2 = SpeechSegment(
            start_time=now + timedelta(seconds=7.5),
            end_time=now + timedelta(seconds=12.5),
            audio=np.random.randn(5 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        merged = merger.add_segments_batch([seg1, seg2])

        # Should merge (gap <= threshold)
        assert len(merged) == 1


class TestBoundaryConditions:
    """Tests for boundary conditions."""

    def test_zero_duration_segment(self):
        """Test handling of zero-duration segment."""
        config = Config()
        merger = SegmentMerger(config)

        sample_rate = 16000
        now = datetime.now()

        seg = SpeechSegment(
            start_time=now,
            end_time=now,  # Zero duration
            audio=np.array([], dtype=np.float32),
            sample_rate=sample_rate
        )

        merged = merger.add_segments_batch([seg])

        # Should handle gracefully
        assert merged == [] or len(merged) == 1

    def test_audio_normalization(self):
        """Test audio preprocessing doesn't clip."""
        from audio_capture.preprocess import AudioPreprocessor

        config = Config()
        config.preprocessing.enable_denoising = False
        config.preprocessing.gain_normalization = True
        preprocessor = AudioPreprocessor(config)

        # Very loud audio
        loud_audio = np.ones(16000, dtype=np.float32) * 10.0

        result = preprocessor.preprocess(loud_audio, 16000)

        # Should not clip
        assert np.max(np.abs(result.audio)) < 1.0

    def test_negative_gap_segments(self):
        """Test handling of overlapping segments."""
        config = Config()
        merger = SegmentMerger(config)

        sample_rate = 16000
        now = datetime.now()

        # Overlapping segments
        seg1 = SpeechSegment(
            start_time=now,
            end_time=now + timedelta(seconds=10),
            audio=np.random.randn(10 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        seg2 = SpeechSegment(
            start_time=now + timedelta(seconds=8),  # Overlaps by 2s
            end_time=now + timedelta(seconds=15),
            audio=np.random.randn(7 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        merged = merger.add_segments_batch([seg1, seg2])

        # Should handle overlap gracefully
        assert len(merged) >= 1
