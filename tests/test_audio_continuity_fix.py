from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import io
import json
import wave
from pathlib import Path
from unittest.mock import Mock
import numpy as np
import pytest
from flask import Flask
from scipy.io.wavfile import write


def test_capture_and_media_do_not_wait_for_asr_lock(test_config):
    from utils.data_lock import data_lock, capture_lock, media_lock
    with data_lock(test_config):
        with capture_lock(test_config, timeout=.05), media_lock(test_config, timeout=.05):
            pass
        with pytest.raises(TimeoutError):
            with data_lock(test_config, timeout=.01):
                pass


def test_adc_timestamps_follow_hardware_even_when_callback_is_delayed(monkeypatch):
    from audio_capture.capture import AudioCapture
    import queue
    capture = AudioCapture.__new__(AudioCapture)
    capture.sample_rate = 16000
    capture.is_muted = False
    capture.ring_buffer = Mock()
    capture.chunk_queue = queue.Queue()
    monkeypatch.setattr('audio_capture.capture.time.time', lambda: 1000)
    capture._audio_callback(np.zeros((1600, 1)), 1600, SimpleNamespace(inputBufferAdcTime=5., currentTime=5.2), False)
    monkeypatch.setattr('audio_capture.capture.time.time', lambda: 1010)
    capture._audio_callback(np.zeros((1600, 1)), 1600, SimpleNamespace(inputBufferAdcTime=5.1, currentTime=5.3), False)
    first, second = capture.chunk_queue.get(), capture.chunk_queue.get()
    assert (second.timestamp-first.timestamp).total_seconds() == .1


def test_new_staging_is_lossless_pcm_and_cleanup_understands_flac(test_config):
    from processing.batch_processor import StagingQueue
    from vad.silero_vad import SpeechSegment
    import subprocess
    queue = StagingQueue(test_config)
    audio = np.random.default_rng(3).uniform(-.9, .9, 16000).astype(np.float32)
    start = datetime.now(timezone.utc)
    queue.stage_segment(SpeechSegment(start, start+timedelta(seconds=1), audio, 16000))
    staged = queue.get_pending_segments()[0]
    assert Path(staged.audio_path).suffix == '.flac'
    pcm = subprocess.run(['ffmpeg','-v','error','-i',staged.audio_path,'-f','s16le','-'],capture_output=True,check=True).stdout
    assert np.array_equal(np.frombuffer(pcm,'<i2'), (audio*32767).astype(np.int16))
    queue.mark_processed(staged.segment_id)
    assert not Path(staged.audio_path).exists()


def test_prompt_echo_is_flagged_and_no_longer_supplied(test_config):
    from asr.language_policy import prompt_echo, PROMPT
    from processing.live_pipeline import assess
    assert PROMPT is None
    text = 'आज की बातचीत। Shreyansh, Shivangi. Hindi and English.'
    assert prompt_echo(text)
    assert assess({'text':text,'language':'hi'}, test_config) == 'suspected_prompt_echo'
    assert not prompt_echo('Shivangi से कल बात हुई।')


def test_full_playback_retains_room_audio_while_verified_playback_has_gap(test_config):
    from storage.journal_store import JournalStore
    from web.journal_api import register_journal_api
    from storage.conversation_audio import conversation_audio
    store = JournalStore(test_config)
    # Initialize the existing decision schema without loading a speaker model.
    from speaker_id.voice_gate import SCHEMA
    with store.connect() as conn:
        conn.executescript(SCHEMA)
    root=Path(test_config.database.path).parent.parent
    source=root/'room.wav'; a=root/'left.wav'; b=root/'right.wav'
    root.mkdir(parents=True,exist_ok=True)
    write(source,16000,np.full(48000,2000,np.int16))
    write(a,16000,np.full(16000,1000,np.int16));write(b,16000,np.full(16000,1000,np.int16))
    start=datetime(2026,10,16,tzinfo=timezone.utc)
    details=json.dumps(dict(start_ts=start.isoformat(),end_ts=(start+timedelta(seconds=3)).isoformat()))
    with store.connect() as conn:
        conn.execute('INSERT INTO speaker_filter_decisions VALUES (?,?,?,?,?)',('parent','accepted_spans',str(source),details,start.isoformat()))
    rows=[dict(id='parent__0',conversation_id=123,start_ts=start.isoformat(),end_ts=(start+timedelta(seconds=1)).isoformat(),audio_path=str(a),clean_path=None),dict(id='parent__1',conversation_id=123,start_ts=(start+timedelta(seconds=2)).isoformat(),end_ts=(start+timedelta(seconds=3)).isoformat(),audio_path=str(b),clean_path=None)]
    path=conversation_audio(rows,'original',test_config)
    with wave.open(str(path)) as wav: speech=np.frombuffer(wav.readframes(wav.getnframes()),'<i2')
    assert np.all(speech[16000:32000]==0)
    assert speech[0]==speech[15999]==0
    # Route uses ledger's full source and does not call any ASR component.
    class Connection:
        def execute(self, sql, args):
            if 'journal_segments' in sql: return SimpleNamespace(fetchall=lambda: rows)
            with store.connect() as conn: found=conn.execute(sql,args).fetchone()
            return SimpleNamespace(fetchone=lambda: found)
        def close(self): pass
    app=Flask(__name__);register_journal_api(app,test_config,Connection)
    response=app.test_client().get('/api/conversation/123/audio/full')
    assert response.status_code==200
    with wave.open(io.BytesIO(response.data)) as wav:
        room=np.frombuffer(wav.readframes(wav.getnframes()),'<i2')
    assert np.all(room[16000:32000]==2000)


def test_groq_minute_limit_defers_instead_of_triggering_cpu_fallback(test_config):
    from asr.groq_client import GroqClient, GroqDeferredError
    from storage.journal_store import JournalStore
    store = JournalStore(test_config)
    client = GroqClient(test_config, store)
    test_config.transcription.requests_per_minute = 1
    test_config.transcription.budget_fraction = 1
    client.reserve(1)
    with pytest.raises(GroqDeferredError) as exc:
        client.reserve(1)
    assert 1 <= exc.value.retry_after <= 61
