"""Exercise the actual consumer across the lock timeout that killed production capture."""

import queue
from types import SimpleNamespace
from unittest.mock import Mock

from daemon_v2 import VoiceJournalDaemon


def daemon_stub():
    daemon = VoiceJournalDaemon.__new__(VoiceJournalDaemon)
    daemon.is_running = True
    daemon._shutdown_requested = False
    daemon.is_paused = False
    daemon.config = SimpleNamespace(transcription=SimpleNamespace(capture_chunk_seconds=6))
    daemon.stats = {"errors": 0}
    return daemon


def test_idle_lock_timeout_does_not_kill_consumer_or_block_next_chunk():
    daemon = daemon_stub()
    daemon.audio_buffer = Mock()
    chunk = SimpleNamespace(duration=6)
    daemon.audio_buffer.get.side_effect = [queue.Empty(), chunk, None]
    daemon._flush_continuous = Mock(side_effect=[TimeoutError("enrollment busy"), None])
    daemon._process_vad_buffer = Mock()
    daemon._vad_worker()
    daemon._process_vad_buffer.assert_called_once_with([chunk])
    assert daemon.stats["vad_lock_retries"] == 1


def test_staging_lock_timeout_retries_same_audio_without_dropping_or_appending():
    daemon = daemon_stub()
    chunk = SimpleNamespace(duration=6)
    daemon.audio_buffer = Mock()
    daemon.audio_buffer.get.side_effect = [chunk, None]
    daemon._flush_continuous = Mock()
    daemon._process_vad_buffer = Mock(side_effect=[TimeoutError("busy"), None])
    daemon._vad_worker()
    assert daemon._process_vad_buffer.call_count == 2
    assert all(call.args == ([chunk],) for call in daemon._process_vad_buffer.call_args_list)
    assert daemon.audio_buffer.get.call_count == 2


def test_idle_flush_does_not_take_the_enrollment_lock():
    daemon = daemon_stub()
    daemon.continuous = SimpleNamespace(start=None)
    # No config database path exists: taking the lock would fail this test.
    daemon._flush_continuous()


def test_watchdog_restarts_a_dead_consumer_and_drains_queued_audio():
    daemon = daemon_stub()
    daemon.audio_buffer = queue.Queue()
    daemon.audio_buffer.put(SimpleNamespace(duration=6))
    daemon.audio_buffer.put(None)
    daemon.vad_thread = Mock(is_alive=lambda: False)
    daemon._process_vad_buffer = Mock()
    daemon._flush_continuous = Mock()
    daemon._check_vad_worker()
    daemon.vad_thread.join(timeout=2)
    assert not daemon.vad_thread.is_alive()
    daemon._process_vad_buffer.assert_called_once()
    assert daemon.stats["vad_worker_restarts"] == 1


def test_latest_journal_orders_by_date_before_time_of_day(test_config, monkeypatch):
    import base64
    import importlib
    from pathlib import Path

    from storage.journal_store import JournalStore

    web = importlib.import_module("web.app")
    store = JournalStore(test_config)
    store.import_csv(
        b"date,start_time,end_time,text\n2026-10-15,23:59:00,23:59:01,Older\n2026-10-16,01:00:00,01:00:01,Newer\n"
    )
    monkeypatch.setattr(web, "DB_PATH", store.path)
    monkeypatch.setattr(web, "APP_CONFIG", test_config)
    monkeypatch.setattr(web, "AUDIO_CACHE_PATH", Path(test_config.dashboard.audio_cache_path))
    monkeypatch.setattr(web, "require_external_storage", lambda _: None)
    monkeypatch.setattr(web, "AUTH_USERNAME", "test")
    monkeypatch.setattr(web, "AUTH_PASSWORD", "test")
    headers = {"Authorization": "Basic " + base64.b64encode(b"test:test").decode()}
    response = web.app.test_client().get("/api/conversations?limit=1", headers=headers)
    assert response.status_code == 200
    assert response.json[0]["date"] == "2026-10-16"
    assert response.json[0]["raw_transcript"] == "Newer"
    assert web.get_last_conversation_id() == response.json[0]["conversation_id"]
