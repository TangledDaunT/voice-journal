"""Voice Journal package; heavyweight capture dependencies load on demand."""

from config.settings import Config

__version__ = "2.0.0"
__author__ = "Shreyansh"
__all__ = ["Config", "VoiceJournalDaemon"]


def __getattr__(name):
    if name == "VoiceJournalDaemon":
        from daemon_v2 import VoiceJournalDaemon

        return VoiceJournalDaemon
    raise AttributeError(name)
