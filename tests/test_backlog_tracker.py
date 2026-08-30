"""Tests for backlog tracking module."""

import pytest
import tempfile
import os
from datetime import datetime
from pathlib import Path

from storage.database import BacklogTracker
from config.settings import Config


class TestBacklogTracker:
    """Tests for BacklogTracker class."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_backlog.db"
        config = Config()
        config.database.path = str(db_path)
        return config

    def test_init(self, temp_db):
        """Test backlog tracker initialization."""
        tracker = BacklogTracker(temp_db)
        status = tracker.get_status()

        assert status["total_hours"] == 0.0
        assert status["segment_count"] == 0

    def test_add_segment(self, temp_db):
        """Test adding a segment to backlog."""
        tracker = BacklogTracker(temp_db)

        tracker.add_segment("test_seg_1", 30.0)  # 30 seconds
        status = tracker.get_status()

        assert status["total_hours"] == pytest.approx(30.0 / 3600, rel=0.01)
        assert status["segment_count"] == 1

    def test_add_multiple_segments(self, temp_db):
        """Test adding multiple segments."""
        tracker = BacklogTracker(temp_db)

        tracker.add_segment("seg_1", 60.0)  # 1 minute
        tracker.add_segment("seg_2", 120.0)  # 2 minutes
        tracker.add_segment("seg_3", 180.0)  # 3 minutes

        status = tracker.get_status()

        assert status["total_hours"] == pytest.approx(360.0 / 3600, rel=0.01)  # 6 min total
        assert status["segment_count"] == 3

    def test_remove_segment(self, temp_db):
        """Test removing a processed segment."""
        tracker = BacklogTracker(temp_db)

        tracker.add_segment("seg_1", 60.0)
        tracker.add_segment("seg_2", 60.0)

        status_before = tracker.get_status()
        assert status_before["segment_count"] == 2

        tracker.remove_segment("seg_1")
        status_after = tracker.get_status()

        assert status_after["segment_count"] == 1
        assert status_after["total_hours"] == pytest.approx(60.0 / 3600, rel=0.01)

    def test_overflow_detection(self, temp_db):
        """Test detection of backlog overflow."""
        temp_db.scheduler.backlog_overflow_hours = 24.0
        tracker = BacklogTracker(temp_db)

        # Add 25 hours of audio
        tracker.add_segment("seg_1", 25 * 3600)
        status = tracker.get_status()

        assert status["is_overflow"] == True
