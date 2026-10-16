"""Cross-process exclusion for capture, processing, import and deletion."""

import fcntl
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def data_lock(config, timeout=35):
    path = Path(config.database.path).parent.parent / ".data.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Processing is busy; try again shortly") from None
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_json(path, data):
    import json
    import os
    import tempfile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(data, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


@contextmanager
def capture_lock(config, timeout=35):
    """Protect capture staging from clear-all without waiting on network/model work."""
    with _named_lock(config, '.capture.lock', timeout):
        yield


@contextmanager
def media_lock(config, timeout=35):
    """Protect playback cache writes from clear-all, independently of ASR."""
    with _named_lock(config, '.media.lock', timeout):
        yield


@contextmanager
def _named_lock(config, name, timeout):
    path = Path(config.database.path).parent.parent / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Storage operation is busy; retry shortly') from None
                time.sleep(.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
