"""Voice Journal Package."""
from .config.settings import Config
from .daemon import VoiceJournalDaemon

__version__ = "1.0.0"
__author__ = "Shreyansh"

__all__ = ["Config", "VoiceJournalDaemon"]
