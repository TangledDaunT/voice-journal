"""Integration checks on temporary storage; never import or clear the real journal."""

import csv
import io
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from flask import Flask

from asr.groq_client import GroqClient, GroqUnavailableError
from processing.batch_processor import StagingQueue
from processing.live_pipeline import LiveProcessor, assess
from storage.journal_store import JournalStore
from vad.silero_vad import SpeechSegment
from web.journal_api import register_journal_api

CSV = b"date,start_time,end_time,text,language,speaker,engine\n2026-10-15,15:00:00,15:00:02,Temporary test journal,en,unknown,imported\n"


@pytest.fixture
def journal(test_config):
    store = JournalStore(test_config)
    app = Flask(__name__)
    register_journal_api(app, test_config, store.connect)
    return store, app.test_client()


def test_csv_import_export_is_dated_atomic_and_idempotent(journal):
    store, client = journal
    result = client.post("/api/data/import", data={"file": (io.BytesIO(CSV), "journal.csv")})
    assert result.status_code == 200 and result.json["imported"] == 1
    again = client.post("/api/data/import", data={"file": (io.BytesIO(CSV), "journal.csv")})
    assert again.json["duplicates"] == 1
    output = client.get("/api/data/export.csv")
    rows = list(csv.DictReader(io.StringIO(output.data.decode())))
    assert rows[0]["date"] == "2026-10-15" and rows[0]["text"] == "Temporary test journal"
    invalid = CSV + b"2026-10-16,20:00:00,19:00:00,invalid,en,unknown,imported\n"
    assert (
        client.post("/api/data/import", data={"file": (io.BytesIO(invalid), "x.csv")}).status_code
        == 400
    )
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM conversations_fts WHERE conversations_fts MATCH 'Temporary'"
            ).fetchone()[0]
            == 1
        )


def test_clear_preserves_database_schema_and_accepts_new_import(journal, test_config, temp_dir):
    store, client = journal
    store.import_csv(CSV)
    audio = temp_dir / "audio" / "2026-10-15" / "private.opus"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"private-audio-test")
    backup = temp_dir / "backups" / "old.db"
    backup.parent.mkdir()
    backup.write_bytes(b"private-backup-test")
    inode = store.path.stat().st_ino
    assert client.post("/api/data/clear", json={}).status_code == 400
    assert audio.exists()
    result = client.post("/api/data/clear", json={"confirmation": "DELETE ALL USER DATA"})
    assert result.status_code == 200 and result.json["database_preserved"]
    assert store.path.exists() and store.path.stat().st_ino == inode
    assert not audio.exists() and not backup.exists()
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM conversations_fts WHERE conversations_fts MATCH 'Temporary'"
            ).fetchone()[0]
            == 0
        )
    assert store.import_csv(CSV)["imported"] == 1


def test_export_zip_contains_database_and_source_audio(journal, temp_dir):
    import zipfile

    store, client = journal
    store.import_csv(CSV)
    path = temp_dir / "audio" / "2026-10-15" / "source.opus"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"original-test-audio")
    response = client.get("/api/data/export.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.read("audio/2026-10-15/source.opus") == b"original-test-audio"
        assert "voice_journal.db" in archive.namelist()
        assert "voice-journal.csv" in archive.namelist()
    response.close()


def test_groq_429_honors_cooldown_and_keeps_accounting(journal, test_config, monkeypatch):
    store, _ = journal
    monkeypatch.setenv("GROQ_API_KEY", "test-only")
    session = Mock()
    session.post.return_value = SimpleNamespace(status_code=429, headers={"retry-after": "60"})
    cloud = GroqClient(test_config, store, session)
    audio = np.full(16000, 0.1, dtype=np.float32)
    with pytest.raises(GroqUnavailableError, match="429"):
        cloud.transcribe(audio, 16000)
    with pytest.raises(GroqUnavailableError, match="cooling"):
        cloud.transcribe(audio, 16000)
    assert session.post.call_count == 1
    with store.connect() as conn:
        row = conn.execute(
            "SELECT audio_seconds,billed_seconds,status FROM groq_requests"
        ).fetchone()
        assert tuple(row) == (1.0, 10.0, "429")


def test_groq_valid_response_and_budget(journal, test_config, monkeypatch):
    store, _ = journal
    monkeypatch.setenv("GROQ_API_KEY", "test-only")
    session = Mock()
    session.post.return_value = SimpleNamespace(
        status_code=200,
        headers={},
        json=lambda: {"text": "test speech", "words": [], "segments": []},
    )
    cloud = GroqClient(test_config, store, session)
    assert cloud.transcribe(np.zeros(32000, dtype=np.float32), 16000)["text"] == "test speech"
    test_config.transcription.daily_requests = 1
    with pytest.raises(GroqUnavailableError, match="budget"):
        cloud.reserve(1)


@pytest.mark.parametrize("cloud_fails,on_battery", [(False, True), (True, False), (True, True)])
def test_live_worker_groq_on_battery_and_local_fallback(
    test_config, monkeypatch, cloud_fails, on_battery
):
    import processing.live_pipeline as live

    monkeypatch.setattr(live, "require_external_storage", lambda _: None)
    monkeypatch.setattr(
        live.psutil, "sensors_battery", lambda: SimpleNamespace(power_plugged=not on_battery)
    )
    monkeypatch.setattr(live.psutil.Process, "nice", lambda self, *args: None)
    queue = StagingQueue(test_config)
    start = datetime(2026, 10, 15, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    audio = np.sin(np.arange(32000) * 0.1).astype(np.float32) * 0.1
    queue.stage_segment(SpeechSegment(start, start + timedelta(seconds=2), audio, 16000))
    staged = queue.get_pending_segments()[0]
    worker = LiveProcessor(test_config, queue)
    worker.groq = Mock()
    if cloud_fails:
        worker.groq.transcribe.side_effect = GroqUnavailableError("test outage")
    else:
        worker.groq.transcribe.return_value = {
            "text": "Test speech",
            "language": "en",
            "words": [],
            "segments": [],
        }
    local = Mock()
    local.transcribe_merged_segment.return_value = SimpleNamespace(
        text="Test local speech", language="en", words=[], confidence_metrics=None
    )
    worker.local = local
    worker.process(staged)
    if cloud_fails and on_battery:
        assert queue.get_pending_segments()
        assert worker.state["status"] == "local_waiting_for_ac"
        local.transcribe_merged_segment.assert_not_called()
    else:
        assert not queue.get_pending_segments()
        with worker.store.connect() as conn:
            row = conn.execute("SELECT * FROM journal_segments").fetchone()
        assert row["engine"] == ("local" if cloud_fails else "groq")
        from pathlib import Path

        assert Path(row["audio_path"]).is_file() and Path(row["clean_path"]).is_file()
        assert row["start_ts"].endswith("+05:30")


def test_hallucination_flags_preserve_high_confidence_common_phrase(test_config):
    assert (
        assess({"text": "thanks for watching", "segments": [{"avg_logprob": -0.1}]}, test_config)
        == "ok"
    )
    assert (
        assess({"text": "thanks for watching", "segments": [{"avg_logprob": -2}]}, test_config)
        == "suspected_hallucination"
    )
    assert assess({"text": "", "segments": []}, test_config) == "rejected_silence"


def test_actual_detail_route_returns_note_and_missing_note_is_404(
    journal, test_config, monkeypatch
):
    import base64
    import importlib

    web = importlib.import_module("web.app")
    store, _ = journal
    store.import_csv(CSV)
    with store.connect() as conn:
        cid = conn.execute("SELECT conversation_id FROM conversations").fetchone()[0]
    monkeypatch.setattr(web, "require_external_storage", lambda _: None)
    monkeypatch.setattr(web, "DB_PATH", store.path)
    monkeypatch.setattr(web, "APP_CONFIG", test_config)
    monkeypatch.setattr(
        web, "AUDIO_CACHE_PATH", __import__("pathlib").Path(test_config.dashboard.audio_cache_path)
    )
    monkeypatch.setattr(web, "AUTH_USERNAME", "test")
    monkeypatch.setattr(web, "AUTH_PASSWORD", "test-password")
    headers = {"Authorization": "Basic " + base64.b64encode(b"test:test-password").decode()}
    client = web.app.test_client()
    response = client.get(f"/api/conversation/{cid}", headers=headers)
    assert response.status_code == 200
    assert response.json["raw_transcript"] == "Temporary test journal"
    assert response.json["engine"] == "imported"
    assert client.get("/api/conversation/1", headers=headers).status_code == 404
    assert client.get(f"/api/conversation/{cid}").status_code == 401


def test_mute_api_removes_flag_on_unmute(journal, test_config, temp_dir, monkeypatch):
    import base64
    import importlib

    web = importlib.import_module("web.app")
    monkeypatch.setattr(web, "require_external_storage", lambda _: None)
    monkeypatch.setattr(web, "AUTH_USERNAME", "test")
    monkeypatch.setattr(web, "AUTH_PASSWORD", "test-password")
    flag = temp_dir / "mute_flag"
    monkeypatch.setattr(web, "MUTE_FILE", flag)
    headers = {"Authorization": "Basic " + base64.b64encode(b"test:test-password").decode()}
    client = web.app.test_client()
    assert client.post("/api/mute", json={"muted": True}, headers=headers).json["muted"] is True
    assert flag.exists()
    assert client.post("/api/mute", json={"muted": False}, headers=headers).json["muted"] is False
    assert not flag.exists()
    assert client.get("/api/mute/status", headers=headers).json["muted"] is False
