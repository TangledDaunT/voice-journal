"""Tests for StagingQueue."""

import pytest
import tempfile
from pathlib import Path

from processing.batch_processor import StagingQueue
from vad.silero_vad import SpeechSegment
from config.settings import Config
from datetime import datetime, timedelta
import numpy as np


class TestStagingQueue:
    """Tests for StagingQueue."""

    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Create temporary storage directory."""
        storage = tmp_path / "audio"
        storage.mkdir()
        return storage

    @pytest.fixture
    def config(self, temp_storage, tmp_path):
        """Create test config."""
        config = Config()
        config.audio.audio_storage_path = str(temp_storage)
        config.database.path = str(tmp_path / "test.db")
        return config

    def test_init(self, config):
        """Test queue initialization."""
        queue = StagingQueue(config)
        assert queue.staging_dir.exists()

    def test_stage_segment(self, config):
        """Test staging a segment."""
        queue = StagingQueue(config)

        sample_rate = 16000
        segment = SpeechSegment(
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(seconds=5),
            audio=np.random.randn(5 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        segment_id = queue.stage_segment(segment)

        assert segment_id is not None

        # Check backlog updated
        status = queue.get_backlog_status()
        assert status["segment_count"] == 1

    def test_get_pending_empty(self, config):
        """Test get_pending with no segments."""
        queue = StagingQueue(config)

        pending = queue.get_pending_segments()

        assert pending == []

    def test_mark_processed(self, config):
        """Test marking segment as processed."""
        queue = StagingQueue(config)

        # Stage a segment
        sample_rate = 16000
        segment = SpeechSegment(
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(seconds=5),
            audio=np.random.randn(5 * sample_rate).astype(np.float32),
            sample_rate=sample_rate
        )

        segment_id = queue.stage_segment(segment)

        # Mark as processed
        queue.mark_processed(segment_id)

        # Check backlog
        status = queue.get_backlog_status()
        # Segment should still be in table but marked processed
        assert status["segment_count"] == 0
