"""Tests for status CLI."""

import pytest
from unittest.mock import patch, Mock
from datetime import datetime

from status import get_status, format_status
from config.settings import Config


class TestGetStatus:
    """Tests for get_status function."""

    @pytest.fixture
    def config(self, temp_dir):
        """Create test config with temp paths."""
        config = Config()
        config.database.path = str(temp_dir / "test.db")
        return config

    def test_get_status_returns_dict(self, config):
        """Test that get_status returns a dict."""
        status = get_status(config)

        assert isinstance(status, dict)
        assert "timestamp" in status
        assert "backlog" in status
        assert "database" in status
        assert "config" in status

    def test_get_status_includes_backlog(self, config):
        """Test that status includes backlog info."""
        status = get_status(config)

        assert "total_hours" in status["backlog"]
        assert "segment_count" in status["backlog"]

    def test_get_status_includes_config_summary(self, config):
        """Test that status includes config summary."""
        status = get_status(config)

        assert "asr_model" in status["config"]
        assert "compute_type" in status["config"]
        assert "backlog_threshold" in status["config"]


class TestFormatStatus:
    """Tests for format_status function."""

    def test_format_text(self):
        """Test text formatting."""
        status = {
            "timestamp": datetime.now().isoformat(),
            "backlog": {
                "total_hours": 5.0,
                "segment_count": 100,
                "growth_warning": False,
                "overflow_threshold": 24.0,
                "is_overflow": False
            },
            "database": {
                "total_last_7_days": 50,
                "with_shivangi": 20,
                "by_quality": {"good": 30, "neutral": 15, "tense": 5}
            },
            "config": {
                "asr_model": "large-v3",
                "compute_type": "int8"
            }
        }

        output = format_status(status, format="text")

        assert "VOICE JOURNAL STATUS" in output
        assert "5.0 hours" in output
        assert "100" in output

    def test_format_json(self):
        """Test JSON formatting."""
        import json

        status = {
            "timestamp": datetime.now().isoformat(),
            "backlog": {"total_hours": 0},
            "database": {},
            "config": {}
        }

        output = format_status(status, format="json")

        # Should be valid JSON
        parsed = json.loads(output)
        assert parsed == status
