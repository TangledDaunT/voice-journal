"""Speech-only daily journal daemon: capture, detect speech, transcribe, and store."""

import queue
import signal
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from asr.transcriber import ASRProcessor
from audio_capture.capture import AudioCapture
from config.settings import Config
from speaker_id.identification import SpeakerMatch
from storage.daily_journal import DailyJournal
from utils.logger import logger, setup_logging
from vad.silero_vad import VADProcessor


class VoiceJournalDaemon:
    """Continuously records speech and appends it to the current daily journal."""

    def __init__(self, config_path: Optional[str] = None):
        default_config_path = Path(__file__).parent / "config" / "default_config.yaml"
        self.config = Config.from_yaml(config_path or str(default_config_path))
        setup_logging(
            log_level=self.config.daemon.log_level,
            log_file=self.config.daemon.log_file,
        )
        self.is_running = False
        self.is_paused = False
        self._shutdown_requested = False
        self.audio_queue = queue.Queue(maxsize=100)
        self.vad_queue = queue.Queue(maxsize=50)
        self.vad_processor = VADProcessor(self.config)
        self.asr_processor = ASRProcessor(self.config)
        self.daily_journal = DailyJournal(self.config)
        self._unknown_speaker = SpeakerMatch("unknown", 0.0, 0.0, 0.0, {})
        self.audio_capture = AudioCapture(
            self.config,
            on_chunk=lambda chunk: self.audio_queue.put(chunk)
            if not self.is_paused else None,
        )
        self.stats = {"segments_detected": 0, "segments_transcribed": 0, "errors": 0}

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._shutdown_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        self.threads = [
            threading.Thread(target=self._vad_worker, daemon=True, name="VADWorker"),
            threading.Thread(target=self._transcription_worker, daemon=True, name="ASRWorker"),
        ]
        for thread in self.threads:
            thread.start()
        self.audio_capture.start()
        logger.info("Speech-only daily journal started")
        while self.is_running and not self._shutdown_requested:
            time.sleep(1)
        self.stop()

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        self._shutdown_requested = True
        self.audio_capture.stop()
        self.audio_queue.put(None)
        self.vad_queue.put(None)
        for thread in self.threads:
            thread.join(timeout=5)
        logger.info("Speech-only daily journal stopped: %s", self.stats)

    def pause(self):
        self.is_paused = True
        self.audio_capture.mute()

    def resume(self):
        self.is_paused = False
        self.audio_capture.unmute()

    def _signal_handler(self, signum, frame):
        logger.info("Received signal %s", signum)
        self._shutdown_requested = True

    def _vad_worker(self):
        audio_buffer = []
        buffer_duration = 0.0
        buffer_max = 30.0
        while self.is_running and not self._shutdown_requested:
            try:
                chunk = self.audio_queue.get(timeout=1)
                if chunk is None:
                    break
                audio_buffer.append(chunk)
                buffer_duration += chunk.duration
                if buffer_duration >= buffer_max:
                    self._process_vad_buffer(audio_buffer)
                    audio_buffer, buffer_duration = [], 0.0
            except queue.Empty:
                if audio_buffer:
                    self._process_vad_buffer(audio_buffer)
                    audio_buffer, buffer_duration = [], 0.0
            except Exception:
                self.stats["errors"] += 1
                logger.exception("VAD worker error")
        if audio_buffer:
            self._process_vad_buffer(audio_buffer)

    def _process_vad_buffer(self, chunks):
        import numpy as np

        audio = np.concatenate([chunk.audio for chunk in chunks])
        segments = self.vad_processor.process_audio_chunk(audio, chunks[0].timestamp)
        for segment in segments:
            self.vad_queue.put(segment)
            self.stats["segments_detected"] += 1

    def _transcription_worker(self):
        while self.is_running and not self._shutdown_requested:
            try:
                segment = self.vad_queue.get(timeout=1)
                if segment is None:
                    break
                transcript = self.asr_processor.transcribe_with_timing(
                    segment, self._unknown_speaker, self.stats["segments_detected"]
                )
                self.daily_journal.record(segment, transcript)
                if transcript:
                    self.stats["segments_transcribed"] += 1
            except queue.Empty:
                continue
            except Exception:
                self.stats["errors"] += 1
                logger.exception("Transcription/storage worker error")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Voice Journal daily speech daemon")
    parser.add_argument("--config", "-c")
    parser.add_argument("--mute", "-m", action="store_true")
    args = parser.parse_args()
    daemon = VoiceJournalDaemon(args.config)
    if args.mute:
        daemon.pause()
    daemon.start()


if __name__ == "__main__":
    main()
