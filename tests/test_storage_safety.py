"""Storage safety checks use temporary paths and never the production drive."""

from pathlib import Path

import pytest

from utils.storage_guard import StorageUnavailableError, require_external_storage


def test_unmounted_drive_creates_nothing(test_config, temp_dir, monkeypatch):
    root = temp_dir / "missing-drive"
    monkeypatch.setenv("DATA_ROOT", str(root))
    with pytest.raises(StorageUnavailableError, match="drive missing"):
        require_external_storage(test_config)
    assert not root.exists()


def test_mounted_drive_rejects_escape(test_config, temp_dir, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(temp_dir))
    monkeypatch.setattr(Path, "is_mount", lambda self: self == temp_dir)
    with pytest.raises(StorageUnavailableError, match="outside DATA_ROOT"):
        require_external_storage(test_config)


def test_web_fails_closed_and_all_routes_require_auth(test_config, temp_dir, monkeypatch):
    import importlib

    web = importlib.import_module("web.app")

    monkeypatch.setattr(web, "APP_CONFIG", test_config)
    monkeypatch.setattr(web, "AUTH_USERNAME", "audit")
    monkeypatch.setattr(web, "AUTH_PASSWORD", "test-only-password")
    monkeypatch.setattr(web, "DB_PATH", temp_dir / "must-not-create.db")
    monkeypatch.setenv("DATA_ROOT", str(temp_dir / "absent"))
    client = web.app.test_client()
    for route in ["/", "/conversations/1", "/notes/private.md", "/assets/test.js", "/api/stats"]:
        assert client.get(route).status_code == 401
    auth = {"Authorization": "Basic YXVkaXQ6dGVzdC1vbmx5LXBhc3N3b3Jk"}
    assert client.get("/api/stats", headers=auth).status_code == 503
    status = client.get("/api/storage", headers=auth)
    assert status.status_code == 503
    assert status.json["available"] is False
    assert client.get("/health").status_code == 500
    assert not web.DB_PATH.exists()


def test_suspect_legacy_text_is_preserved_and_flagged(monkeypatch):
    import importlib

    web = importlib.import_module("web.app")
    import sqlite3
    monkeypatch.setattr(web, "audio_url_for", lambda _: None)
    monkeypatch.setattr(web, "get_db_connection", lambda: sqlite3.connect(":memory:"))
    row = {
        "id": 1, "conversation_id": 1, "date": "2026-10-15",
        "start_time": "12:00:00", "end_time": "12:00:01", "duration_seconds": 1,
        "participants": '[]', "languages": '["en"]', "source_type": "unknown",
        "is_shivangi_conversation": 0, "quality": "unknown", "summary": "derived text",
        "raw_transcript": "Use only Hindi and English", "transcript": "legacy text",
        "cleaned_transcript": "rewritten text",
    }
    result = web.conversation_payload(row)
    assert result["raw_transcript"] == row["raw_transcript"]
    assert result["review_flags"] == ["suspected_hallucination"]
    assert result["audio_url"] is None
