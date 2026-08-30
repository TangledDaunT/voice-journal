"""Tests for batch scheduler module."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from processing.batch_processor import BatchScheduler
from config.settings import Config


class TestBatchScheduler:
    """Tests for BatchScheduler class."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        config = Config()
        config.scheduler.cpu_idle_threshold = 30.0
        config.scheduler.min_idle_duration_seconds = 60
        config.scheduler.daytime_batch_hours = 0.5
        config.scheduler.overnight_batch_hours = 2.0
        config.scheduler.guaranteed_window_start_hour = 22
        config.scheduler.guaranteed_window_end_hour = 6
        return config

    def test_init(self, config):
        """Test scheduler initialization."""
        mock_processor = Mock()
        scheduler = BatchScheduler(config, mock_processor)

        assert scheduler.config == config
        assert scheduler.batch_processor == mock_processor
        assert scheduler.is_processing == False

    def test_guaranteed_window_overnight(self, config):
        """Test guaranteed window detection at night."""
        mock_processor = Mock()
        scheduler = BatchScheduler(config, mock_processor)

        # 11 PM (within window)
        assert scheduler._in_guaranteed_window(23) == True

        # 3 AM (within window)
        assert scheduler._in_guaranteed_window(3) == True

    def test_guaranteed_window_daytime(self, config):
        """Test guaranteed window outside overnight."""
        mock_processor = Mock()
        scheduler = BatchScheduler(config, mock_processor)

        # 10 AM (outside window)
        assert scheduler._in_guaranteed_window(10) == False

        # 3 PM (outside window)
        assert scheduler._in_guaranteed_window(15) == False

    def test_cpu_idle_detection(self, config):
        """Test CPU idle detection."""
        mock_processor = Mock()
        scheduler = BatchScheduler(config, mock_processor)

        with patch('psutil.cpu_percent') as mock_cpu:
            mock_cpu.return_value = 20.0  # Below threshold

            result = scheduler._check_cpu_idle()

            assert result == True
            assert scheduler.idle_start_time is not None

    def test_cpu_busy_detection(self, config):
        """Test CPU busy detection."""
        mock_processor = Mock()
        scheduler = BatchScheduler(config, mock_processor)

        with patch('psutil.cpu_percent') as mock_cpu:
            mock_cpu.return_value = 50.0  # Above threshold

            result = scheduler._check_cpu_idle()

            assert result == False
            assert scheduler.idle_start_time is None

    def test_batch_chunk_size_daytime(self, config):
        """Test batch chunk size calculation for daytime."""
        mock_processor = Mock()
        mock_processor.staging_queue = Mock()
        mock_processor.staging_queue.get_backlog_status.return_value = {"total_hours": 1.0}

        scheduler = BatchScheduler(config, mock_processor)

        # Mock daytime (not in window)
        with patch.object(scheduler, '_in_guaranteed_window', return_value=False), \
             patch.object(scheduler, '_check_cpu_idle', return_value=True):

            scheduler.idle_start_time = datetime.now()

            # Patch run_batch to capture args
            mock_processor.run_batch = Mock()

            scheduler._check_and_run()

            # Should be called with max_segments based on daytime_batch_hours
            call_args = mock_processor.run_batch.call_args
            max_segments = call_args[1]['max_segments']
            # daytime_batch_hours (0.5) * 3600 / 10 seconds per segment = 180 segments
            assert max_segments == 180

    def test_batch_chunk_size_overnight(self, config):
        """Test batch chunk size calculation for overnight."""
        mock_processor = Mock()
        mock_processor.staging_queue = Mock()
        mock_processor.staging_queue.get_backlog_status.return_value = {"total_hours": 1.0}

        scheduler = BatchScheduler(config, mock_processor)

        # Mock overnight (in window)
        with patch.object(scheduler, '_in_guaranteed_window', return_value=True):

            # Patch run_batch to capture args
            mock_processor.run_batch = Mock()

            scheduler._check_and_run()

            # Should be called with max_segments based on overnight_batch_hours
            call_args = mock_processor.run_batch.call_args
            max_segments = call_args[1]['max_segments']
            # overnight_batch_hours (2.0) * 3600 / 10 seconds per segment = 720 segments
            assert max_segments == 720

    def test_skip_if_already_processing(self, config):
        """Test that scheduler skips if already processing."""
        mock_processor = Mock()
        scheduler = BatchScheduler(config, mock_processor)

        scheduler.is_processing = True

        # Should return early without checking anything
        scheduler._check_and_run()

        # run_batch should not be called
        mock_processor.run_batch.assert_not_called()

    def test_backlog_overflow_triggers_fallback(self, config):
        """Test that backlog overflow triggers fallback model."""
        mock_processor = Mock()
        mock_processor.staging_queue = Mock()
        mock_processor.staging_queue.get_backlog_status.return_value = {
            "total_hours": 30.0  # Exceeds threshold
        }

        scheduler = BatchScheduler(config, mock_processor)

        with patch.object(scheduler, '_in_guaranteed_window', return_value=True):
            mock_processor.run_batch = Mock()

            scheduler._check_and_run()

            # Should be called with use_fallback=True
            call_args = mock_processor.run_batch.call_args
            assert call_args[1]['use_fallback'] == True
