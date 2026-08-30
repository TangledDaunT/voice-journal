"""Tests for Obsidian output with confidence markers."""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile

from obsidian.output import ObsidianWriter
from conversation.grouping import ConversationUnit
from llm_output.classifier import ClassificationResult
from config.settings import Config


class TestObsidianWriter:
    """Tests for ObsidianWriter."""

    @pytest.fixture
    def temp_vault(self, tmp_path):
        """Create a temporary vault."""
        vault = tmp_path / "vault"
        vault.mkdir()
        return vault

    @pytest.fixture
    def config(self, temp_vault):
        """Create test config."""
        config = Config()
        config.obsidian.vault_path = str(temp_vault)
        return config

    def test_init(self, config, temp_vault):
        """Test writer initialization."""
        writer = ObsidianWriter(config)

        assert writer.vault_path == temp_vault

    def test_creates_directories(self, config, temp_vault):
        """Test that directories are created."""
        writer = ObsidianWriter(config)

        daily_path = temp_vault / config.obsidian.daily_notes_dir
        conv_path = temp_vault / config.obsidian.conversation_notes_dir

        # Directories should exist on init
        assert daily_path.exists()
        assert conv_path.exists()

    def test_create_slug(self, config):
        """Test slug creation."""
        writer = ObsidianWriter(config)

        assert writer._create_slug("This is a test summary") == "this-is-a-test-summ"
        assert writer._create_slug("Hello, world!") == "hello-world"
        assert writer._create_slug("") == "conversation"
