"""Tests for segment merger module."""

import numpy as np
from datetime import datetime, timedelta
import pytest

from vad.segment_merger import SegmentMerger, MergedSegment
from vad.silero_vad import SpeechSegment
from config.settings import Config


def create_test_segment(duration_seconds: float, start_time: datetime) -> SpeechSegment:
    """Create a test speech segment."""
    sample_rate = 16000
    samples = int(duration_seconds * sample_rate)
    audio = np.random.randn(samples).astype(np.float32) * 0.1

    return SpeechSegment(
        start_time=start_time,
        end_time=start_time + timedelta(seconds=duration_seconds),
        audio=audio,
        sample_rate=sample_rate
    )


class TestSegmentMerger:
    """Tests for SegmentMerger class."""

    def test_init(self):
        """Test merger initialization."""
        config = Config()
        merger = SegmentMerger(config)

        assert merger.merge_gap_seconds == config.segment_merging.merge_gap_seconds
        assert merger.min_unit_seconds == config.segment_merging.min_transcription_unit_seconds

    def test_single_segment(self):
        """Test merging single segment."""
        config = Config()
        merger = SegmentMerger(config)

        seg = create_test_segment(10.0, datetime.now())
        merged = merger.add_segments_batch([seg])

        assert len(merged) == 1
        assert merged[0].merge_count == 1
        assert merged[0].duration_seconds == 10.0

    def test_merge_adjacent_segments(self):
        """Test merging segments separated by small gap."""
        config = Config()
        config.segment_merging.merge_gap_seconds = 2.5
        merger = SegmentMerger(config)

        now = datetime.now()
        seg1 = create_test_segment(5.0, now)
        seg2 = create_test_segment(5.0, now + timedelta(seconds=6))
        # Gap is 1 second (within merge threshold)

        merged = merger.add_segments_batch([seg1, seg2])

        assert len(merged) == 1
        assert merged[0].merge_count == 2

    def test_no_merge_large_gap(self):
        """Test that segments with large gap are not merged."""
        config = Config()
        config.segment_merging.merge_gap_seconds = 2.5
        merger = SegmentMerger(config)

        now = datetime.now()
        seg1 = create_test_segment(5.0, now)
        seg2 = create_test_segment(5.0, now + timedelta(seconds=10))
        # Gap is 5 seconds (exceeds merge threshold)

        merged = merger.add_segments_batch([seg1, seg2])

        assert len(merged) == 2

    def test_minimum_unit_duration(self):
        """Test that short segments are handled appropriately."""
        config = Config()
        config.segment_merging.min_transcription_unit_seconds = 5.0
        merger = SegmentMerger(config)

        now = datetime.now()
        seg = create_test_segment(2.0, now)  # Too short

        merged = merger.add_segments_batch([seg])

        # Should still return something (policy is to keep, not discard)
        assert len(merged) == 1
