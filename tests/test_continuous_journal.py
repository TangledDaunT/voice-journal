"""Continuity, language gates and listening tests use temporary data and fake speech."""

import io
import json
import wave
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from flask import Flask
from scipy.io.wavfile import write

from asr.language_policy import violation
from audio_capture.monitor import MicrophoneMonitor
from storage.conversation_audio import conversation_audio
from storage.journal_store import JournalStore
from vad.continuous import ContinuousSpeech
from web.microphone_api import register_microphone_api

START = datetime(2026, 10, 16, 12, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_uninterrupted_multichunk_samples_are_exactly_once_and_ordered():
    def detector(audio):
        return [(0, len(audio), 0.9)]

    stream = ContinuousSpeech(detector)
    source = np.random.default_rng(4).normal(0, 0.1, 16000 * 60).astype(np.float32)
    emitted = []
    for offset in range(0, len(source), 16000 * 6):
        emitted += stream.feed(
            source[offset : offset + 16000 * 6], START + timedelta(seconds=offset / 16000)
        )
    emitted += stream.feed(np.empty(0), START + timedelta(seconds=60), flush=True)
    assert len(emitted) >= 3
    assert all(s.duration_seconds <= 24 for s in emitted)
    assert np.array_equal(
        np.concatenate([s.audio[s.core_start_samples : s.core_end_samples] for s in emitted]),
        source,
    )
    assert all(
        a.start_time + timedelta(seconds=a.core_end_samples / 16000)
        == b.start_time + timedelta(seconds=b.core_start_samples / 16000)
        for a, b in zip(emitted, emitted[1:], strict=False)
    )


def test_natural_pauses_keep_audio_until_flush():
    stream = ContinuousSpeech(lambda audio: [(0, 4 * 16000, 0.9), (5 * 16000, 11 * 16000, 0.9)])
    first = np.ones(6 * 16000, np.float32)
    assert stream.feed(first, START) == []
    last = np.concatenate([np.ones(5 * 16000), np.zeros(16000)]).astype(np.float32)
    emitted = stream.feed(last, START + timedelta(seconds=6))
    assert len(emitted) == 1 and emitted[0].duration_seconds == 12
    assert np.array_equal(emitted[0].audio, np.concatenate([first, last]))


def save_clip(store, key, offset, text, speaker="Shreyansh", duration=3, audio_path=None):
    start = START + timedelta(seconds=offset)
    return store.save(
        key,
        start,
        start + timedelta(seconds=duration),
        text,
        {"text": text},
        "groq",
        language="en",
        speaker=speaker,
        audio_path=audio_path,
        clean_path=audio_path,
    )


def test_conversation_turns_retry_silence_gap_and_csv(test_config):
    store = JournalStore(test_config)
    cid = save_clip(store, "one", 0, "First sentence.")
    assert save_clip(store, "two", 4, "दूसरा वाक्य।", "Shivangi") == cid
    assert save_clip(store, "two", 4, "Must not duplicate", "Shivangi") == cid
    assert save_clip(store, "three", 25, "New conversation") != cid
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 2
        conversation = conn.execute(
            "SELECT * FROM conversations WHERE conversation_id=?", (cid,)
        ).fetchone()
        assert conversation["raw_transcript"] == "First sentence.\nदूसरा वाक्य।"
        assert json.loads(conversation["participants"]) == ["Shreyansh", "Shivangi"]
        assert conversation["duration_seconds"] == 7
    assert len(store.export_csv().splitlines()) == 4  # quoted multiline field


def test_legacy_unique_schema_migrates_without_losing_provenance(test_config):
    store = JournalStore(test_config)
    cid = save_clip(store, "old", 0, "preserved")
    with store.connect() as conn:
        conn.execute("CREATE UNIQUE INDEX legacy_unique ON journal_segments(conversation_id)")
        # Reproduce the exact original table definition with inline UNIQUE.
        conn.execute("ALTER TABLE journal_segments RENAME TO old")
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='old'").fetchone()[0]
        conn.execute(
            sql.replace('"old"', "journal_segments").replace(
                "conversation_id INTEGER,", "conversation_id INTEGER UNIQUE,"
            )
        )
        conn.execute("INSERT INTO journal_segments SELECT * FROM old")
        conn.execute("DROP TABLE old")
    store = JournalStore(test_config)
    assert save_clip(store, "new", 3, "continued") == cid
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM journal_segments").fetchone()[0] == 2
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_playable_audio_keeps_silence_and_only_supplied_verified_clips(test_config):
    store = JournalStore(test_config)
    root = Path(test_config.audio.audio_storage_path)
    root.mkdir()
    a, b = root / "a.wav", root / "b.wav"
    write(a, 16000, np.full(32000, 1200, np.int16))
    write(b, 16000, np.full(32000, -1200, np.int16))
    cid = save_clip(store, "a", 0, "one", duration=2, audio_path=a)
    assert save_clip(store, "b", 3, "two", duration=2, audio_path=b) == cid
    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM journal_segments ORDER BY start_ts").fetchall()
    path = conversation_audio(rows, "original", test_config)
    with wave.open(str(path)) as wav:
        assert wav.getnframes() == 5 * 16000
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), "<i2")
    assert np.all(pcm[80:31920] == 1200)
    assert np.all(pcm[32000:48000] == 0)
    assert np.all(pcm[48080:-80] == -1200)


@pytest.mark.parametrize(
    "text,language,expected",
    [
        ("आज meeting 2:30 बजे है। Yes, ₹500!", "hi", None),
        ("English punctuation: “yes!” 123", "English", None),
        ("привет", "hi", "unexpected_script"),
        ("こんにちは", "en", "unexpected_script"),
        ("سلام", "ur", "unexpected_language"),
        ("Romanized output", "ru", "unexpected_language"),
    ],
)
def test_language_policy(text, language, expected):
    assert violation({"text": text, "language": language}) == expected


def test_monitor_lease_buffers_expire_and_stop_without_enabling_journal(test_config, monkeypatch):
    import web.microphone_api as api

    monkeypatch.setattr(api, "require_external_storage", lambda _: None)
    app = Flask(__name__)
    register_microphone_api(app, test_config)
    client = app.test_client()
    monitor = MicrophoneMonitor(test_config)
    chunk = SimpleNamespace(audio=np.full((4096, 1), 0.1), sample_rate=16000)
    monitor.feed(chunk)
    assert not monitor.active
    assert client.get("/api/microphone/audio").status_code == 204
    assert client.post("/api/microphone/listen", json={"enabled": True}).status_code == 200
    monitor.feed(chunk)
    response = client.get("/api/microphone/audio")
    assert response.status_code == 200
    with wave.open(io.BytesIO(response.data)) as wav:
        assert wav.getnframes() == 4096
    sequence = response.headers["X-Audio-Sequence"]
    assert client.get("/api/microphone/audio?after=" + sequence).status_code == 204
    assert client.post("/api/microphone/listen", json={"enabled": False}).status_code == 200
    assert monitor.buffer.read(0) is None
    assert client.get("/api/microphone/audio").status_code == 204


def test_boundary_word_ownership_uses_time_not_repeated_word_heuristics():
    from asr.boundaries import owned_words

    payload = {
        "words": [
            {"word": "yes", "start": 0.1, "end": 0.3},
            {"word": "yes,", "start": 0.4, "end": 0.6},
            {"word": "आज!", "start": 0.6, "end": 0.9},
        ]
    }
    left, status = owned_words(payload, 0, 8000, 16000)
    right, status2 = owned_words(payload, 8000, 16000, 16000)
    assert (left, right, status, status2) == ("yes", "yes, आज!", None, None)
    assert owned_words({"text": "untimed"}, 0, 16000, 16000)[1] == "boundary_timestamps_missing"


@pytest.mark.parametrize(
    "retry_text,retry_lang,expected",
    [("आज meeting है।", "Hindi", "ok"), ("привет", "Russian", "unexpected_language")],
)
def test_cloud_policy_retries_and_preserves_raw_responses(
    test_config, monkeypatch, retry_text, retry_lang, expected
):
    from processing.batch_processor import StagingQueue
    from processing.live_pipeline import LiveProcessor
    from vad.silero_vad import SpeechSegment

    monkeypatch.setattr("processing.live_pipeline.require_external_storage", lambda _: None)
    queue = StagingQueue(test_config)
    queue.stage_segment(
        SpeechSegment(START, START + timedelta(seconds=3), np.full(48000, 0.1, np.float32), 16000)
    )
    worker = LiveProcessor(test_config, queue)
    worker.groq.transcribe = Mock(
        side_effect=[
            {"text": "سلام", "language": "Urdu"},
            {"text": retry_text, "language": retry_lang},
        ]
    )
    worker.process(queue.get_pending_segments()[0])
    with worker.store.connect() as conn:
        row = conn.execute("SELECT * FROM journal_segments").fetchone()
    raw = json.loads(row["raw_json"])
    assert raw["policy_first_response"]["text"] == "سلام"
    assert raw["text"] == retry_text and row["status"] == expected
    assert worker.groq.transcribe.call_args.kwargs["language"] == "hi"
    if expected != "ok":
        assert row["text_raw"] == "[Transcript needs language review]"


def test_local_policy_retries_hindi_and_keeps_actual_provider_language(test_config, monkeypatch):
    from asr.transcriber_batch import BatchASRProcessor
    from vad.segment_merger import MergedSegment

    monkeypatch.setattr(BatchASRProcessor, "_init_model", lambda self: None)
    processor = BatchASRProcessor(test_config)

    def segment(text):
        return SimpleNamespace(text=text, no_speech_prob=0.01, avg_logprob=-0.1, words=[])

    processor.model = Mock()
    processor.model.transcribe.side_effect = [
        (iter([segment("привет")]), SimpleNamespace(language="ru", language_probability=0.9)),
        (
            iter([segment("आज meeting है।")]),
            SimpleNamespace(language="hi", language_probability=0.9),
        ),
    ]
    unit = MergedSegment(
        START, START + timedelta(seconds=3), np.full(48000, 0.1, np.float32), 16000, []
    )
    result = processor.transcribe_merged_segment(unit)
    assert result.text == "आज meeting है।" and result.language == "hi"
    assert result.raw_payload["policy_first_response"]["text"] == "привет"
    assert processor.model.transcribe.call_args.kwargs["language"] == "hi"


def test_local_persistent_unexpected_script_is_reviewed_without_relabel(test_config, monkeypatch):
    from asr.transcriber_batch import BatchASRProcessor
    from vad.segment_merger import MergedSegment

    monkeypatch.setattr(BatchASRProcessor, "_init_model", lambda self: None)
    processor = BatchASRProcessor(test_config)
    processor.model = Mock()

    def transcribe(*args, **kwargs):
        segment = SimpleNamespace(text="привет", no_speech_prob=0.01, avg_logprob=-0.1, words=[])
        return iter([segment]), SimpleNamespace(language="ru", language_probability=0.9)

    processor.model.transcribe.side_effect = transcribe
    unit = MergedSegment(
        START, START + timedelta(seconds=3), np.full(48000, 0.1, np.float32), 16000, []
    )
    result = processor.transcribe_merged_segment(unit)
    assert result.text == "[Transcript needs language review]"
    assert result.language == "ru" and result.policy_status == "unexpected_language"
    assert result.raw_payload["text"] == "привет"
    assert list((Path(test_config.audio.audio_storage_path).parent / "asr_review").glob("*.json"))


def test_named_microphone_missing_never_opens_default_input(test_config, monkeypatch):
    from audio_capture.capture import AudioCapture

    test_config.audio.input_device = "external-only"
    monkeypatch.setattr(
        "audio_capture.capture.sd.query_devices",
        lambda: [{"name": "builtin", "max_input_channels": 1}],
    )
    stream = Mock()
    monkeypatch.setattr("audio_capture.capture.sd.InputStream", stream)
    capture = AudioCapture(test_config)
    capture._start_stream()
    stream.assert_not_called()
    assert capture.selected_device is None and "missing" in capture.device_error
    test_config.audio.input_card = "PCH"
    test_config.audio.input_jack_control = "Mic Jack"
    monkeypatch.setattr("audio_capture.alsa_guard.jack_connected", lambda *args: False)
    assert not capture.check_input()
    assert "disconnected" in capture.device_error


def test_continuous_units_flow_into_one_conversation_without_overlap_words(
    test_config, monkeypatch
):
    from processing.batch_processor import StagingQueue
    from processing.live_pipeline import LiveProcessor

    monkeypatch.setattr("processing.live_pipeline.require_external_storage", lambda _: None)
    stream = ContinuousSpeech(lambda a: [(0, len(a), 0.9)])
    source = np.random.default_rng(6).normal(0, 0.1, 16000 * 50).astype(np.float32)
    units = []
    for offset in range(0, len(source), 96000):
        units.extend(
            stream.feed(source[offset : offset + 96000], START + timedelta(seconds=offset / 16000))
        )
    units.extend(stream.feed(np.empty(0), START + timedelta(seconds=50), flush=True))
    queue = StagingQueue(test_config)
    worker = LiveProcessor(test_config, queue)
    expected = [f"word{i}" for i in range(50)]
    for unit in units:
        start_offset = (unit.start_time - START).total_seconds()
        words = [
            {"word": word, "start": i + 0.5 - start_offset, "end": i + 0.7 - start_offset}
            for i, word in enumerate(expected)
            if start_offset <= i + 0.6 < start_offset + len(unit.audio) / 16000
        ]
        worker.groq.transcribe = Mock(
            return_value={
                "text": " ".join(w["word"] for w in words),
                "language": "en",
                "words": words,
            }
        )
        queue.stage_segment(unit)
        worker.process(queue.get_pending_segments()[0])
    with worker.store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1
        row = conn.execute("SELECT * FROM conversations").fetchone()
        assert row["raw_transcript"].split() == expected
        rows = conn.execute("SELECT * FROM journal_segments ORDER BY start_ts").fetchall()
    with wave.open(str(conversation_audio(rows, "original", test_config))) as wav:
        assert wav.getnframes() == 50 * 16000


def test_listening_routes_require_existing_basic_auth(monkeypatch):
    import importlib

    web = importlib.import_module("web.app")

    monkeypatch.setattr(web, "AUTH_USERNAME", "test")
    monkeypatch.setattr(web, "AUTH_PASSWORD", "test-password")
    client = web.app.test_client()
    assert client.post("/api/microphone/listen", json={"enabled": True}).status_code == 401
    assert client.get("/api/microphone/audio").status_code == 401


def test_talkback_stop_waits_for_inflight_native_audio_write(monkeypatch):
    import base64
    import importlib
    import threading
    from concurrent.futures import ThreadPoolExecutor

    web = importlib.import_module("web.app")
    monkeypatch.setattr(web, "require_external_storage", lambda _: None)
    monkeypatch.setattr(web, "AUTH_USERNAME", "test")
    monkeypatch.setattr(web, "AUTH_PASSWORD", "test")
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()

    class Stream:
        def write(self, audio):
            entered.set()
            assert release.wait(2)
            assert not stopped.is_set()

        def stop(self):
            stopped.set()

        def close(self):
            assert stopped.is_set()

    monkeypatch.setattr(web, "talkback_output_stream", Stream())
    monkeypatch.setattr(web, "talkback_active", True)
    headers = {"Authorization": "Basic " + base64.b64encode(b"test:test").decode()}

    def request_write():
        return (
            web.app.test_client()
            .post("/api/talkback/stream", data=b"\0\0" * 512, headers=headers)
            .status_code
        )

    def request_stop():
        return web.app.test_client().post("/api/talkback/stop", headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        writing = pool.submit(request_write)
        assert entered.wait(2)
        closing = pool.submit(request_stop)
        assert not stopped.wait(0.1)
        release.set()
        assert writing.result() == closing.result() == 200
    assert stopped.is_set()
