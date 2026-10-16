"""Short-clip Groq-first processing; recording callbacks never run ASR/network work."""

import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import psutil

from asr.groq_client import GroqClient, GroqDeferredError, GroqUnavailableError
from asr.transcriber_batch import BatchASRProcessor
from speaker_id.voice_gate import SpeakerModelUnavailableError, VoiceGate
from storage.journal_store import JournalStore
from utils.data_lock import data_lock, write_json
from audio_capture.sound_profile import filters as sound_filters
from utils.logger import logger
from utils.storage_guard import require_external_storage
from vad.segment_merger import MergedSegment
from vad.silero_vad import SpeechSegment


def assess(payload, config):
    from asr.language_policy import violation, prompt_echo

    if prompt_echo(payload.get("text", "")):
        return "suspected_prompt_echo"

    if violation(payload):
        return violation(payload)
    segments = payload.get("segments") or []
    low = any(
        s.get("no_speech_prob", 0) > config.asr.no_speech_prob_threshold
        or s.get("avg_logprob", 0) < config.asr.avg_logprob_threshold
        or s.get("compression_ratio", 0) > config.asr.compression_ratio_threshold
        for s in segments
    )
    text = payload.get("text", "")
    repeated = BatchASRProcessor._has_repetition_loop(text)
    signature = any(
        p in text.lower()
        for p in [
            "thanks for watching",
            "amara.org",
            "use only hindi and english",
            "do not output any other language",
        ]
    )
    if not text.strip():
        return "rejected_silence"
    if repeated or (signature and low):
        return "suspected_hallucination"
    return "low_confidence" if low else "ok"


class LiveProcessor:
    def __init__(self, config, queue):
        require_external_storage(config)
        self.config = config
        self.staging_queue = queue
        self.store = JournalStore(config)
        self.groq = GroqClient(config, self.store)
        self.voice_gate = VoiceGate(config, self.store)
        self.local = None
        self.defer_until = 0.0
        self._stop = threading.Event()
        self._thread = None
        self.is_processing = False
        self.state_path = Path(config.database.path).parent.parent / "runtime/processing.json"
        self.state = {
            "engine": None,
            "status": "waiting_for_speech",
            "last_success_at": None,
            "last_error": None,
        }
        self.generation = None
        self._state()

    def _state(self, **values):
        self.state.update(values)
        self.state["updated_at"] = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
        write_json(self.state_path, self.state)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True, name="groq-first-worker")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=35)

    def get_status(self):
        return dict(self.state, currently_processing=self.is_processing)

    def _loop(self):
        while not self._stop.is_set():
            try:
                require_external_storage(self.config)
                generation_path = self.state_path.parent / "data_generation"
                generation = generation_path.read_text() if generation_path.exists() else ""
                if self.generation is not None and generation != self.generation:
                    self.state = {
                        "engine": None,
                        "status": "waiting_for_speech",
                        "last_success_at": None,
                        "last_error": None,
                    }
                self.generation = generation
                if self._handle_enrollment():
                    self._stop.wait(0.25)
                    continue
                if self.config.speaker.enrolled_only and not self.voice_gate.profiles(True):
                    self._state(status="enrollment_required", engine=None, last_error=None)
                    self._stop.wait(1)
                    continue
                if time.monotonic() < self.defer_until:
                    self._stop.wait(.5)
                    continue
                pending = self.staging_queue.get_pending_segments(limit=1)
                if not pending:
                    self._state(status="waiting_for_speech", engine=None)
                else:
                    with data_lock(self.config):
                        self.process(pending[0])
            except SpeakerModelUnavailableError:
                self._state(
                    status="speaker_model_unavailable",
                    engine=None,
                    last_error="Speaker verification unavailable; no audio is sent to ASR",
                )
            except Exception as exc:
                # Never include server responses, keys or transcript content in logs.
                logger.error("Journal worker failed: {}", type(exc).__name__)
                self._state(status="error", last_error=type(exc).__name__, engine=None)
            self._stop.wait(1)

    def _handle_enrollment(self):
        path = self.state_path.parent / "enrollment.json"
        try:
            state = json.loads(path.read_text())
        except (OSError, ValueError):
            return False
        if state.get("status") in ("queued", "recording"):
            self._state(status="calibrating", engine=None)
            return True
        if state.get("status") != "analyzing":
            return False
        with data_lock(self.config):
            if not path.exists():
                return True
            latest = json.loads(path.read_text())
            if latest.get("id") != state["id"] or latest.get("status") != "analyzing":
                return True
            try:
                from scipy.io.wavfile import read

                sr, audio = read(state["audio_path"])
                if sr != 16000:
                    raise ValueError("Calibration recording has the wrong sample rate")
                audio = audio.astype(np.float32) / 32767.0
                result = self.voice_gate.enroll(state["name"], audio, state["id"])
                write_json(path, dict(state, status="complete", profile=result, audio_path=None))
                self._state(status="waiting_for_speech", engine=None, last_error=None)
            except ValueError as exc:
                write_json(path, dict(state, status="error", error=str(exc), audio_path=None))
            except Exception:
                write_json(
                    path,
                    dict(
                        state,
                        status="error",
                        error="Speaker model could not process this sample. No voice profile was saved.",
                        audio_path=None,
                    ),
                )
            finally:
                Path(state["audio_path"]).unlink(missing_ok=True)
        return True

    def process(self, staged):
        if not self.config.speaker.enrolled_only:
            return self._process_allowed(staged)
        if not Path(staged.audio_path).is_file():
            return
        with self.store.connect() as conn:
            done = conn.execute(
                "SELECT 1 FROM speaker_filter_decisions WHERE source_id=?", (staged.segment_id,)
            ).fetchone()
        if done:
            self.staging_queue.mark_processed(staged.segment_id)
            return
        segment = self.staging_queue.load_segment_audio(staged)
        self._state(status="verifying_speaker", engine=None)
        spans, details = self.voice_gate.classify(segment.audio, segment.sample_rate)
        if details.get("reason") == "no_enrolled_speakers":
            self._state(status="enrollment_required", engine=None)
            return
        from dataclasses import asdict, replace

        for span in spans:
            core_start = max(span.start, segment.core_start_samples)
            core_end = min(span.end, segment.core_end_samples or len(segment.audio))
            if core_end <= core_start:
                continue
            child = replace(
                staged,
                segment_id=f"{staged.segment_id}__{span.start}_{span.end}",
                start_time=segment.start_time + timedelta(seconds=span.start / segment.sample_rate),
                end_time=segment.start_time + timedelta(seconds=span.end / segment.sample_rate),
                duration_seconds=(span.end - span.start) / segment.sample_rate,
            )
            cropped = SpeechSegment(
                child.start_time,
                child.end_time,
                segment.audio[span.start : span.end],
                segment.sample_rate,
                core_start_samples=core_start - span.start,
                core_end_samples=core_end - span.start,
            )
            if not self._process_allowed(child, cropped, span):
                return
        directory = (
            Path(self.config.audio.audio_storage_path).parent
            / "audio_filtered"
            / segment.start_time.strftime("%Y-%m-%d")
        )
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / Path(staged.audio_path).name
        if not source.exists():
            shutil.copyfile(staged.audio_path, source)
        details.update(
            spans=[asdict(span) for span in spans],
            start_ts=segment.start_time.isoformat(),
            end_ts=segment.end_time.isoformat(),
            model="resemblyzer-0.1.4-256d",
        )
        with self.store.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO speaker_filter_decisions VALUES (?,?,?,?,?)",
                (
                    staged.segment_id,
                    "accepted_spans" if spans else "excluded",
                    str(source),
                    json.dumps(details),
                    datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                ),
            )
        self.staging_queue.mark_processed(staged.segment_id)
        if not spans:
            self._state(
                status="background_skipped",
                engine=None,
                last_error=None,
                last_filter_reason=details["reason"],
            )

    def _process_allowed(self, staged, segment=None, speaker=None):
        if not Path(staged.audio_path).exists():
            return
        if self.store.has_segment(staged.segment_id):
            return True
        self.is_processing = True
        started = time.monotonic()
        try:
            require_external_storage(self.config)
            segment = segment or self.staging_queue.load_segment_audio(staged)
            audio = segment.audio
            rms = 20 * np.log10(max(float(np.sqrt(np.mean(audio * audio))), 1e-10))
            engine = "none"
            model = ""
            fallback_reason = None
            if rms < self.config.preprocessing.min_rms_db_for_asr:
                payload = {"text": "", "segments": [], "input_rms_db": float(rms)}
                status = "rejected_silence"
            else:
                self._state(status="uploading", engine="groq", last_error=None)
                try:
                    payload = self.groq.transcribe(audio, segment.sample_rate)
                    engine = "groq"
                    model = self.config.transcription.groq_model
                except GroqDeferredError as exc:
                    self.defer_until = time.monotonic() + exc.retry_after
                    self._state(status="cloud_pacing", engine="groq", last_error=None)
                    return False
                except GroqUnavailableError as exc:
                    fallback_reason = str(exc)
                    battery = psutil.sensors_battery()
                    if battery and not battery.power_plugged:
                        self._state(
                            status="local_waiting_for_ac",
                            engine="local",
                            last_error=fallback_reason,
                        )
                        return False
                    self._state(status="transcribing", engine="local", last_error=fallback_reason)
                    if self.local is None:
                        # Niceness applies to this process, including its capture thread.
                        # Keep capture responsive through its dedicated small callback/queue.
                        try:
                            psutil.Process().nice(19)
                        except (psutil.AccessDenied, OSError):
                            pass
                        self.local = BatchASRProcessor(self.config)
                    unit = MergedSegment(
                        segment.start_time, segment.end_time, audio, segment.sample_rate, [segment]
                    )
                    result = self.local.transcribe_merged_segment(unit)
                    if result is None:
                        raise RuntimeError(
                            "Local ASR did not return a result; source remains queued"
                        ) from None
                    metrics = result.confidence_metrics
                    payload = {
                        "text": result.text,
                        "language": result.language,
                        "words": result.words,
                        "segments": [
                            {
                                "no_speech_prob": float(metrics.no_speech_prob),
                                "avg_logprob": float(metrics.avg_logprob),
                            }
                        ]
                        if metrics
                        else [],
                    }
                    if getattr(result, "raw_payload", None):
                        payload = dict(result.raw_payload)
                    engine = "local"
                    model = self.config.asr.model_size
                from asr.language_policy import violation

                if violation(payload) and not payload.get("policy_retry_language"):
                    first = payload
                    try:
                        if engine == "groq":
                            payload = self.groq.transcribe(
                                audio, segment.sample_rate, language="hi"
                            )
                        else:
                            retry = self.local.transcribe_merged_segment(unit, language="hi")
                            payload = dict(self.local.last_raw_payload) if retry else first
                        payload = dict(
                            payload, policy_first_response=first, policy_retry_language="hi"
                        )
                    except GroqUnavailableError:
                        payload = dict(first, policy_retry_failed=True)
                status = assess(payload, self.config)
                if status in ("unexpected_language", "unexpected_script", "suspected_prompt_echo"):
                    payload = dict(payload, review_reason=status)

            # Half-second verified context protects forced boundaries. Each timed word
            # belongs to one core by its midpoint; original provider payload stays intact.
            core_start = segment.core_start_samples
            core_end = segment.core_end_samples or len(segment.audio)
            owned_text = payload.get("text", "")
            if core_start or core_end < len(segment.audio):
                from asr.boundaries import owned_words

                owned_text, boundary_status = owned_words(
                    payload, core_start, core_end, segment.sample_rate
                )
                payload = dict(
                    payload,
                    core_start_samples=core_start,
                    core_end_samples=core_end,
                    owned_text=owned_text,
                )
                if boundary_status:
                    status = boundary_status
                original_start = segment.start_time
                segment = SpeechSegment(
                    original_start + timedelta(seconds=core_start / segment.sample_rate),
                    original_start + timedelta(seconds=core_end / segment.sample_rate),
                    segment.audio[core_start:core_end],
                    segment.sample_rate,
                )
            day = segment.start_time.strftime("%Y-%m-%d")
            original = (
                Path(self.config.audio.audio_storage_path) / day / f"{staged.segment_id}.opus"
            )
            original.parent.mkdir(parents=True, exist_ok=True)
            if Path(staged.audio_path).suffix == ".wav":
                original = original.with_suffix(".wav")
            else:
                original = original.with_suffix(Path(staged.audio_path).suffix)
            if speaker is not None or core_start or core_end < len(audio):
                from scipy.io.wavfile import write

                original = original.with_suffix(".wav")
                write(
                    str(original),
                    segment.sample_rate,
                    (np.clip(segment.audio, -1, 1) * 32767).astype(np.int16),
                )
            elif not original.exists():
                shutil.copyfile(staged.audio_path, original)
            clean = Path(self.config.dashboard.audio_cache_path) / day / f"{staged.segment_id}.ogg"
            clean.parent.mkdir(parents=True, exist_ok=True)
            temporary = clean.with_suffix(".tmp.ogg")
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(original),
                    "-af",
                    sound_filters(self.config),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "32k",
                    str(temporary),
                ],
                check=True,
                capture_output=True,
                timeout=25,
            )
            os.replace(temporary, clean)
            self.store.save(
                staged.segment_id,
                segment.start_time,
                segment.end_time,
                "[Transcript needs language review]"
                if status in ("unexpected_language", "unexpected_script", "suspected_prompt_echo")
                else owned_text,
                payload,
                engine,
                model,
                payload.get("language", ""),
                status,
                original,
                clean,
                speaker=speaker.name if speaker else "unknown",
                speaker_id=speaker.speaker_id if speaker else None,
                speaker_similarity=speaker.similarity if speaker else None,
            )
            if speaker is None:
                self.staging_queue.mark_processed(staged.segment_id)
            self._state(
                status="saved",
                engine=engine,
                last_error=fallback_reason,
                last_success_at=datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                last_latency_seconds=round(time.monotonic() - started, 2),
                last_segment_id=staged.segment_id,
                last_speaker=speaker.name if speaker else None,
            )
            return True
        finally:
            self.is_processing = False
