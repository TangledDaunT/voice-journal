"""Integration tests for segment merger and batch ASR."""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from vad.segment_merger import SegmentMerger
from vad.silero_vad import SpeechSegment
from config.settings import Config


class TestSegmentMergeIntegration:
    """Integration tests for segment merging."""

    def test_merge_creates_continuous_audio(self):
        """Test that merged audio is continuous without gaps."""
        config = Config()
        merger = SegmentMerger(config)

        now = datetime.now()
        sample_rate = 16000

        # Create three segments with small gaps
        seg1 = SpeechSegment(
            start_time=now,
            end_time=now + timedelta(seconds=5),
            audio=np.random.randn(5 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        seg2 = SpeechSegment(
            start_time=now + timedelta(seconds=6),  # 1s gap
            end_time=now + timedelta(seconds=10),
            audio=np.random.randn(4 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        seg3 = SpeechSegment(
            start_time=now + timedelta(seconds=11),  # 1s gap
            end_time=now + timedelta(seconds=16),
            audio=np.random.randn(5 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        merged = merger.add_segments_batch([seg1, seg2, seg3])

        # Should merge into one unit (all gaps < 2.5s)
        assert len(merged) == 1

        # Duration should be total time span
        expected_duration = 16.0  # 0 to 16 seconds
        assert merged[0].duration_seconds == pytest.approx(expected_duration, rel=0.1)

        # Audio length should match duration
        expected_samples = int(expected_duration * sample_rate)
        assert len(merged[0].audio) == pytest.approx(expected_samples, rel=0.01)

    def test_merge_preserves_segment_order(self):
        """Test that segments are merged in chronological order."""
        config = Config()
        merger = SegmentMerger(config)

        now = datetime.now()
        sample_rate = 16000

        # Create segments out of order
        seg1 = SpeechSegment(
            start_time=now + timedelta(seconds=10),
            end_time=now + timedelta(seconds=15),
            audio=np.ones(5 * sample_rate, dtype=np.float32),
            sample_rate=sample_rate
        )

        seg2 = SpeechSegment(
            start_time=now,
            end_time=now + timedelta(seconds=5),
            audio=np.zeros(5 * sample_rate, dtype=np.float32),
            sample_rate=sample_rate
        )

        merged = merger.add_segments_batch([seg1, seg2])

        # Should process in chronological order
        assert merged[0].start_time == now
        assert merged[0].source_segments[0].start_time < merged[0].source_segments[1].start_time
