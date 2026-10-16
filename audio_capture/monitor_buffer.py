"""Bounded shared RAM between Docker's shared IPC namespaces; never persisted audio."""

import fcntl
import hashlib
import mmap
import os
import struct
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SLOTS = 16
PAYLOAD = 65536
SLOT_SIZE = PAYLOAD + 16
SIZE = 64 + SLOTS * SLOT_SIZE
HEADER = struct.Struct("<Qdd")  # sequence, last audio time, listening lease


class MonitorBuffer:
    def __init__(self, config, reset=False):
        key = hashlib.sha256(str(config.database.path).encode()).hexdigest()[:20]
        ram = Path("/dev/shm")
        # macOS test/development fallback; production Docker always uses shared RAM.
        if not ram.is_dir():
            ram = Path(config.database.path).parent.parent / "runtime"
            ram.mkdir(parents=True, exist_ok=True)
        self.path = ram / f"vj-monitor-{key}"
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        self.lock = threading.RLock()
        with self.guard():
            fresh = os.fstat(self.fd).st_size != SIZE
            if fresh:
                os.ftruncate(self.fd, SIZE)
            self.memory = mmap.mmap(self.fd, SIZE)
            if reset or fresh:
                self.memory[:] = b"\0" * SIZE

    @contextmanager
    def guard(self):
        with self.lock:
            fcntl.flock(self.fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(self.fd, fcntl.LOCK_UN)

    @property
    def active(self):
        with self.guard():
            return HEADER.unpack_from(self.memory)[2] > time.time()

    def lease(self, enabled):
        with self.guard():
            sequence, updated, _ = HEADER.unpack_from(self.memory)
            if enabled:
                HEADER.pack_into(self.memory, 0, sequence, updated, time.time() + 8)
            else:
                self.memory[:] = b"\0" * SIZE

    def clear_expired(self):
        with self.guard():
            sequence, _, lease = HEADER.unpack_from(self.memory)
            if sequence and lease <= time.time():
                self.memory[:] = b"\0" * SIZE

    def publish(self, blob):
        if len(blob) > PAYLOAD:
            raise ValueError("Live microphone block exceeds shared buffer size")
        with self.guard():
            sequence, _, lease = HEADER.unpack_from(self.memory)
            if lease <= time.time():
                return
            sequence = sequence + 1 if sequence else time.time_ns()
            offset = 64 + (sequence % SLOTS) * SLOT_SIZE
            struct.pack_into("<QI", self.memory, offset, sequence, len(blob))
            self.memory[offset + 16 : offset + 16 + len(blob)] = blob
            HEADER.pack_into(self.memory, 0, sequence, time.time(), lease)

    def read(self, after):
        with self.guard():
            latest, updated, lease = HEADER.unpack_from(self.memory)
            if not latest or lease <= time.time() or time.time() - updated > 2:
                return None
            sequence = (
                latest if not after or after < latest - SLOTS + 1 or after > latest else after + 1
            )
            if sequence > latest:
                return None
            offset = 64 + (sequence % SLOTS) * SLOT_SIZE
            saved, length = struct.unpack_from("<QI", self.memory, offset)
            if saved != sequence or length > PAYLOAD:
                return None
            return sequence, self.memory[offset + 16 : offset + 16 + length]

    def close(self):
        self.memory.close()
        os.close(self.fd)
