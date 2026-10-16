"""Fail closed before runtime I/O if the journal drive is unavailable."""

import os
from pathlib import Path


class StorageUnavailableError(RuntimeError):
    """The required external journal storage cannot be used."""


def require_external_storage(config) -> Path:
    """Validate the mount and configured destinations without creating anything.

    Docker must bind the mounted host drive at /data. The host control script
    checks the source mount; inside Docker /data must itself be a mount point.
    """
    root = Path(os.environ.get("DATA_ROOT", "/mnt/music-drive"))
    if not root.is_absolute() or not root.is_mount() or root == Path("/"):
        raise StorageUnavailableError(f"Journal drive missing: {root}. Mount the external drive first.")
    journal = (root / "voice-journal").resolve()
    destinations = (
        config.audio.audio_storage_path,
        config.database.path,
        config.dashboard.audio_cache_path,
        config.journal.storage_path,
        config.daemon.mute_file,
    )
    for destination in destinations:
        if not Path(destination).resolve().is_relative_to(journal):
            raise StorageUnavailableError("Journal storage path is outside DATA_ROOT/voice-journal.")
    if not os.access(root, os.W_OK):
        raise StorageUnavailableError(f"Journal drive is not writable: {root}.")
    return root
