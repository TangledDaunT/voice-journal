"""Speaker gating and enrollment tests use temporary files and synthetic vectors only."""

import json
import queue
import wave
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from audio_capture.capture import AudioCapture
from processing.batch_processor import StagingQueue
from processing.live_pipeline import LiveProcessor
from speaker_id.enrollment import EnrollmentRecorder
from speaker_id.voice_gate import MODEL_ID, VoiceGate
from storage.journal_store import JournalStore
from utils.data_lock import write_json


def add_profile(store, name, embedding, enabled=True):
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO speaker_profiles VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                name,
                name,
                name.lower(),
                json.dumps([embedding]),
                MODEL_ID,
                int(enabled),
                30,
                20,
                "{}",
                "2026-10-15T20:00:00+05:30",
            ),
        )


@pytest.fixture
def gate(test_config, monkeypatch):
    import speaker_id.voice_gate as module

    monkeypatch.setattr(module, "speech_samples", lambda audio, sample_rate=16000: audio)
    store = JournalStore(test_config)
    encoder = Mock()
    encoder.embed.return_value = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    result = VoiceGate(test_config, store, encoder)
    return result, store, encoder


def test_unknown_and_disabled_speakers_never_pass(gate):
    detector, store, encoder = gate
    add_profile(store, "Shreyansh", [1, 0, 0], enabled=False)
    spans, detail = detector.classify(np.ones(96000, dtype=np.float32) * 0.1)
    assert not spans and detail["reason"] == "no_enrolled_speakers"
    encoder.embed.assert_not_called()
    with store.connect() as conn:
        conn.execute("UPDATE speaker_profiles SET enabled=1")
    encoder.embed.return_value = np.array([0, 0, 1.0], dtype=np.float32)
    spans, _ = detector.classify(np.ones(96000, dtype=np.float32) * 0.1)
    assert not spans


def test_ambiguous_match_is_rejected_instead_of_guessed(gate):
    detector, store, encoder = gate
    add_profile(store, "Shreyansh", [0.84, 0.542586, 0])
    add_profile(store, "Shivangi", [0.84, -0.542586, 0])
    spans, detail = detector.classify(np.ones(96000, dtype=np.float32) * 0.1)
    assert not spans
    assert detail["window_reasons"]["ambiguous_or_overlap"] == 5


def test_only_consistent_matching_time_ranges_are_admitted(gate):
    detector, store, encoder = gate
    add_profile(store, "Shreyansh", [1, 0, 0])
    encoder.embed.side_effect = [
        np.array(v, dtype=np.float32)
        for v in [[1, 0, 0], [1, 0, 0], [0, 0, 1], [0, 0, 1], [0, 0, 1]]
    ]
    spans, _ = detector.classify(np.ones(96000, dtype=np.float32) * 0.1)
    assert [(s.start, s.end, s.name) for s in spans] == [(0, 32000, "Shreyansh")]


def test_enrollment_uses_multiple_positions_and_replaces_same_name(gate):
    detector, store, encoder = gate
    detector.enrollment_detector = lambda audio: [(0, len(audio), 0.9)]
    audio = np.sin(np.arange(30 * 16000) * 0.1).astype(np.float32) * 0.1
    result = detector.enroll("Shreyansh", audio, "id-1")
    assert result["quality"]["prototype_count"] == 3
    assert result["quality"]["accuracy_verified"] is False
    detector.enroll("Shreyansh", audio, "replacement-id")
    assert len(detector.profiles()) == 1
    assert detector.profiles()[0]["id"] == "id-1"
    detector.enrollment_detector = lambda audio: []
    with pytest.raises(ValueError, match="Not enough clear speech"):
        detector.enroll("Shivangi", audio, "id-2")
    assert len(detector.profiles()) == 1


def test_recorder_collects_exactly_30_seconds_and_preserves_mute(test_config, temp_dir):
    recorder = EnrollmentRecorder(test_config)
    request = {
        "id": "recording-test",
        "name": "Shreyansh",
        "requested_at": "2026-10-15T20:00:00+05:30",
    }
    write_json(recorder.state_path, dict(request, status="queued"))
    write_json(recorder.request_path, request)
    flag = temp_dir / "mute_flag"
    flag.write_text("muted")
    recorder.tick()
    for _ in range(117):
        recorder.feed(np.ones(4096, dtype=np.float32) * 0.05)
    state = json.loads(recorder.state_path.read_text())
    assert state["status"] == "recording"
    recorder.feed(np.ones(4096, dtype=np.float32) * 0.05)
    state = json.loads(recorder.state_path.read_text())
    assert state["status"] == "analyzing" and state["seconds_recorded"] == 30
    with wave.open(state["audio_path"]) as audio:
        assert audio.getnframes() == 30 * 16000
    assert not recorder.active and flag.exists()


def test_cancel_does_not_write_calibration_audio(test_config):
    recorder = EnrollmentRecorder(test_config)
    request = {"id": "cancel-test", "name": "Shreyansh"}
    write_json(recorder.state_path, dict(request, status="queued"))
    write_json(recorder.request_path, request)
    recorder.tick()
    recorder.feed(np.ones(16000, dtype=np.float32) * 0.1)
    write_json(recorder.request_path, dict(request, cancel=True))
    recorder.tick()
    assert recorder.state()["status"] == "cancelled"
    assert not recorder.active and not list(recorder.root.glob("calibration/enrollments/*.wav"))


def test_muted_capture_delivers_only_during_requested_calibration(temp_dir):
    capture = AudioCapture.__new__(AudioCapture)
    capture.is_muted = False
    capture.calibration_active = True
    capture.mute_file = temp_dir / "mute_flag"
    capture.mute_file.touch()
    capture.ring_buffer = Mock()
    capture.sample_rate = 16000
    capture.chunk_queue = queue.Queue()
    capture._audio_callback(np.zeros((512, 1), dtype=np.float32), 512, {}, False)
    assert not capture.chunk_queue.empty()
    capture.chunk_queue.get()
    capture.calibration_active = False
    capture.get_mute_status()  # Filesystem state is refreshed outside the hardware callback.
    capture._audio_callback(np.zeros((512, 1), dtype=np.float32), 512, {}, False)
    assert capture.chunk_queue.empty() and capture.mute_file.exists()


@pytest.mark.parametrize("known", [False, True])
def test_pipeline_blocks_unenrolled_audio_before_cloud_and_crops_known_audio(
    test_config, monkeypatch, known
):
    import processing.live_pipeline as live
    import speaker_id.voice_gate as gate_module

    monkeypatch.setattr(live, "require_external_storage", lambda config: None)
    monkeypatch.setattr(gate_module, "speech_samples", lambda audio, sample_rate=16000: audio)
    test_config.speaker.enrolled_only = True
    queue = StagingQueue(test_config)
    start = datetime(2026, 10, 15, 20, tzinfo=ZoneInfo("Asia/Kolkata"))
    from vad.silero_vad import SpeechSegment

    audio = np.sin(np.arange(96000) * 0.1).astype(np.float32) * 0.1
    queue.stage_segment(SpeechSegment(start, start + timedelta(seconds=6), audio, 16000))
    processor = LiveProcessor(test_config, queue)
    processor.groq = Mock()
    processor.groq.transcribe.return_value = {
        "text": "Allowed test speech",
        "language": "en",
        "segments": [],
    }
    if known:
        add_profile(processor.store, "Shreyansh", [1, 0, 0])
        processor.voice_gate.encoder = Mock()
        processor.voice_gate.encoder.embed.side_effect = [
            np.array(v, dtype=np.float32)
            for v in [[1, 0, 0], [1, 0, 0], [0, 0, 1], [0, 0, 1], [0, 0, 1]]
        ]
    processor.process(queue.get_pending_segments()[0])
    if not known:
        processor.groq.transcribe.assert_not_called()
        assert queue.get_pending_segments()
        assert processor.state["status"] == "enrollment_required"
    else:
        assert processor.groq.transcribe.call_args.args[0].shape == (32000,)
        assert not queue.get_pending_segments()
        with processor.store.connect() as conn:
            note = conn.execute("SELECT * FROM journal_segments").fetchone()
            assert note["speaker_id"] == "Shreyansh" and note["speaker_similarity"] == 1
            assert (
                conn.execute("SELECT participants FROM conversations").fetchone()[0]
                == '["Shreyansh"]'
            )
            assert conn.execute("SELECT COUNT(*) FROM speaker_filter_decisions").fetchone()[0] == 1
        with wave.open(note["audio_path"]) as file:
            assert file.getnframes() == 32000
        assert Path(note["clean_path"]).is_file()


def test_unknown_media_is_archived_locally_without_transcription(test_config, monkeypatch):
    import processing.live_pipeline as live
    import speaker_id.voice_gate as module
    from vad.silero_vad import SpeechSegment

    monkeypatch.setattr(live, "require_external_storage", lambda config: None)
    monkeypatch.setattr(module, "speech_samples", lambda audio, sample_rate=16000: audio)
    test_config.speaker.enrolled_only = True
    queue = StagingQueue(test_config)
    start = datetime(2026, 10, 15, 20, tzinfo=ZoneInfo("Asia/Kolkata"))
    audio = np.sin(np.arange(96000) * 0.1).astype(np.float32) * 0.1
    queue.stage_segment(SpeechSegment(start, start + timedelta(seconds=6), audio, 16000))
    processor = LiveProcessor(test_config, queue)
    add_profile(processor.store, "Shreyansh", [1, 0, 0])
    processor.voice_gate.encoder = Mock()
    processor.voice_gate.encoder.embed.return_value = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    processor.groq = Mock()
    processor.process(queue.get_pending_segments()[0])
    processor.groq.transcribe.assert_not_called()
    assert not queue.get_pending_segments()
    with processor.store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
        row = conn.execute("SELECT * FROM speaker_filter_decisions").fetchone()
    assert row["status"] == "excluded" and Path(row["audio_path"]).is_file()


def test_enrollment_api_queues_real_daemon_recording_and_never_returns_embeddings(
    test_config, temp_dir, monkeypatch
):
    from flask import Flask

    import web.speaker_api as api
    from web.journal_api import register_journal_api

    store = JournalStore(test_config)
    detector = VoiceGate(test_config, store, Mock())
    add_profile(store, "Existing", [1, 0, 0])
    path = temp_dir / "fake-package" / "__init__.py"
    path.parent.mkdir()
    path.write_text("")
    (path.parent / "pretrained.pt").write_bytes(b"test-only-package-marker")
    original_find_spec = api.importlib.util.find_spec
    monkeypatch.setattr(
        api.importlib.util,
        "find_spec",
        lambda name: (
            SimpleNamespace(origin=str(path)) if name == "resemblyzer" else original_find_spec(name)
        ),
    )
    write_json(temp_dir / "runtime/capture.json", {"stream_active": True, "muted": True})
    app = Flask("speaker-api-test")
    api.register_speaker_api(app, test_config, store.connect)
    register_journal_api(app, test_config, store.connect)
    client = app.test_client()
    response = client.post("/api/speakers/enroll", json={"name": "Shreyansh"})
    assert response.status_code == 202
    assert response.json["status"] == "queued"
    assert client.post("/api/speakers/enroll", json={"name": "Shivangi"}).status_code == 409
    assert client.post("/api/speakers/enroll", json={"name": "../escape"}).status_code == 400
    listed = client.get("/api/speakers").json
    assert "embeddings" not in listed["profiles"][0]
    assert client.post("/api/speakers/enrollment/cancel").status_code == 200
    assert client.get("/api/speakers/enrollment").json["status"] == "cancelled"
    assert client.patch("/api/speakers/Existing", json={"enabled": False}).status_code == 200
    assert not detector.profiles(True)
    cleared = client.post("/api/data/clear", json={"confirmation": "DELETE ALL USER DATA"})
    assert cleared.status_code == 200
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM speaker_profiles").fetchone()[0] == 0
