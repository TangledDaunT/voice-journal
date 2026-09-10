"""Voice Journal Package."""
try:
    # When installed as a package
    from voice_journal.config.settings import Config
    from voice_journal.daemon import VoiceJournalDaemon
except ImportError:
    # For development when the package is not installed but we are in the source tree
    import os
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from voice_journal.config.settings import Config
    from voice_journal.daemon import VoiceJournalDaemon

__version__ = "1.0.0"
__author__ = "Shreyansh"

__all__ = ["Config", "VoiceJournalDaemon"]