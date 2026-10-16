"""
Main daemon orchestrator for Voice Journal (Refactored for Batch Processing).

Architecture:
- Audio capture + VAD run near-real-time (lightweight)
- VAD segments are staged to disk for batch processing
- Batch processor runs on schedule (idle-triggered + guaranteed overnight window)
- No real-time transcription attempt

This replaces the old real-time pipeline.
"""

import signal
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import queue
import os
import numpy as np

from config.settings import Config
from utils.storage_guard import require_external_storage
from audio_capture.capture import AudioCapture
from vad.silero_vad import VADProcessor, SpeechSegment
from processing.batch_processor import StagingQueue, BatchProcessor, BatchScheduler
from utils.logger import setup_logging, logger, log_stage


class VoiceJournalDaemon:
    """
    Refactored daemon for batch-mode processing.

    Real-time: Audio capture + VAD detection
    Batch: Everything else (merge, preprocess, ASR, speaker ID, grouping, LLM, output)
    """

    def __init__(self, config_path: Optional[str] = None):
        # Load configuration
        if config_path:
            self.config = Config.from_yaml(config_path)
        else:
            self.config = Config()

        require_external_storage(self.config)

        # Setup logging
        setup_logging(
            log_level=self.config.daemon.log_level,
            log_file=self.config.daemon.log_file
        )

        # Initialize lightweight real-time components
        self._init_realtime_components()

        # Initialize batch processing components
        self._init_batch_components()

        # Control flags
        self.is_running = False
        self.is_paused = False
        self._shutdown_requested = False

        # Statistics
        self._reset_epoch = 0.0
        self.stats = {
            'vad_segments_detected': 0,
            'segments_staged': 0,
            'batch_jobs_completed': 0,
            'errors': 0,
            'start_time': None
        }

        logger.info("VoiceJournalDaemon initialized (batch mode)")

    def _init_realtime_components(self):
        """Initialize lightweight real-time components."""
        logger.info("Initializing real-time components...")

        # Stage 1: Audio Capture
        self.staging_queue = StagingQueue(self.config, storage_guard=require_external_storage)

        self.audio_capture = AudioCapture(
            self.config,
            on_chunk=self._handle_audio_chunk
        )

        from audio_capture.monitor import MicrophoneMonitor
        self.monitor = MicrophoneMonitor(self.config)

        from speaker_id.enrollment import EnrollmentRecorder
        self.enrollment = EnrollmentRecorder(self.config, storage_guard=require_external_storage)

        # Stage 2: VAD (lightweight)
        self.vad_processor = VADProcessor(self.config)

        from vad.continuous import ContinuousSpeech
        self.continuous = ContinuousSpeech(self.vad_processor.vad.detect_speech, self.config.audio.sample_rate)

        # Audio buffer for VAD
        self.audio_buffer: queue.Queue = queue.Queue(maxsize=100)

        logger.info("Real-time components initialized")

    def _init_batch_components(self):
        """Initialize batch processing components."""
        logger.info("Initializing batch components...")

        from processing.live_pipeline import LiveProcessor
        self.batch_scheduler = LiveProcessor(self.config, self.staging_queue)
        self.batch_scheduler.voice_gate.enrollment_detector = self.vad_processor.vad.detect_speech
        self.batch_processor = self.batch_scheduler

        logger.info("Batch components initialized")

    def _handle_audio_chunk(self, chunk):
        """Telemetry/enrollment on the queue thread, never in the hardware callback."""
        self.monitor.feed(chunk)
        self.stats['captured_chunks'] = self.stats.get('captured_chunks', 0) + 1
        self.stats['last_audio_at'] = chunk.timestamp.isoformat()
        self.stats['last_delivery_at'] = datetime.now().astimezone().isoformat()
        self.stats['input_rms_db'] = float(20*np.log10(max(float(np.sqrt(np.mean(chunk.audio**2))),1e-10)))
        if self.enrollment.feed(chunk.audio):
            return
        if not self.is_paused and not self.audio_capture.get_mute_status():
            self.audio_buffer.put(chunk)

    def start(self):
        """Start the daemon."""
        if self.is_running:
            logger.warning("Daemon already running")
            return

        self.is_running = True
        self.stats['start_time'] = datetime.now()

        logger.info("="*60)
        logger.info("Voice Journal Daemon Starting (BATCH MODE)")
        logger.info("="*60)

        # Setup signal handlers
        self._setup_signal_handlers()

        # Start processing threads
        self._start_threads()

        # Start audio capture
        self.audio_capture.start()

        # Start batch scheduler
        self.batch_scheduler.start()

        logger.info("Daemon started successfully")
        logger.info("  - Audio capture: RUNNING")
        logger.info("  - VAD: RUNNING")
        logger.info("  - Batch processing: SCHEDULED")

        # Main loop - health check and stats
        self._main_loop()

    def stop(self):
        """Stop the daemon gracefully."""
        if not self.is_running:
            return

        logger.info("Stopping daemon...")

        self.is_running = False
        self._shutdown_requested = True

        # Stop audio capture
        self.audio_capture.stop()

        # Stop batch scheduler
        self.batch_scheduler.stop()

        # Stop threads
        self._stop_threads()

        logger.info("="*60)
        logger.info("Voice Journal Daemon Stopped")
        logger.info(f"Stats: {self.stats}")
        logger.info("="*60)

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        self._shutdown_requested = True

    def _start_threads(self):
        """Start processing threads."""
        # VAD worker thread
        self.vad_thread = threading.Thread(
            target=self._vad_worker,
            daemon=True,
            name="VADWorker"
        )
        self.vad_thread.start()

        logger.info("Started VAD worker thread")

    def _stop_threads(self):
        """Stop processing threads."""
        self.audio_buffer.put(None)  # Signal to stop

        if hasattr(self, 'vad_thread'):
            self.vad_thread.join(timeout=5)

        logger.info("Stopped VAD worker thread")

    def _vad_worker(self):
        """Worker thread for VAD processing and staging."""
        audio_buffer = []
        buffer_duration = 0.0
        buffer_max = self.config.transcription.capture_chunk_seconds  # Process every 30 seconds (was 1800 = 30 min bug)

        while self.is_running and not self._shutdown_requested:
            try:
                # Retry retained audio before accepting more when processing was busy.
                if buffer_duration >= buffer_max:
                    self._process_vad_buffer(audio_buffer)
                    audio_buffer = []
                    buffer_duration = 0.0
                    continue
                try:
                    chunk = self.audio_buffer.get(timeout=1.0)
                except queue.Empty:
                    if audio_buffer:
                        self._process_vad_buffer(audio_buffer)
                        audio_buffer = []
                        buffer_duration = 0.0
                    self._flush_continuous()
                    continue
                if chunk is None:
                    break
                if self.is_paused:
                    continue
                audio_buffer.append(chunk)
                buffer_duration += chunk.duration
            except TimeoutError:
                # Enrollment/ASR can hold the shared lock. This is contention, not
                # permission to terminate the only consumer of the capture queue.
                self.stats['vad_lock_retries'] = self.stats.get('vad_lock_retries', 0) + 1
                time.sleep(0.1)
            except Exception as exc:
                logger.error("VAD worker error: {}", type(exc).__name__)
                self.stats['errors'] += 1
                self.stats['last_vad_error'] = type(exc).__name__
                time.sleep(0.1)

        try:
            if audio_buffer:
                self._process_vad_buffer(audio_buffer)
            self._flush_continuous()
        except Exception as exc:
            logger.error("VAD shutdown flush failed: {}", type(exc).__name__)

    def _flush_continuous(self):
        from datetime import timedelta
        from utils.data_lock import capture_lock
        # There is nothing to protect/flush while muted or calibrating. Avoid
        # taking the ASR/enrollment lock on every idle queue timeout.
        if self.continuous.start is None:
            return
        with capture_lock(self.config):
            epoch = Path(self.config.database.path).parent.parent / 'runtime/reset_epoch'
            if self.continuous.start is None:
                return
            if epoch.exists() and self.continuous.start.timestamp() <= float(epoch.read_text()):
                self.continuous.reset()
                return
            require_external_storage(self.config)
            expected = self.continuous.start + timedelta(seconds=len(self.continuous.audio) / self.config.audio.sample_rate)
            for segment in self.continuous.feed(np.empty(0), expected, flush=True):
                self.staging_queue.stage_segment(segment)
                self.stats['vad_segments_detected'] += 1
                self.stats['segments_staged'] += 1

    def _check_vad_worker(self):
        if self._shutdown_requested or not self.is_running:
            return
        if hasattr(self, 'vad_thread') and not self.vad_thread.is_alive():
            self.stats['vad_worker_restarts'] = self.stats.get('vad_worker_restarts', 0) + 1
            logger.error("VAD worker stopped unexpectedly; restarting consumer")
            self.vad_thread = threading.Thread(target=self._vad_worker, daemon=True, name="VADWorker")
            self.vad_thread.start()

    def _process_vad_buffer(self, chunks: list):
        """Process buffered audio chunks with VAD and stage for batch."""
        import numpy as np

        require_external_storage(self.config)
        from utils.data_lock import capture_lock
        with capture_lock(self.config):
            self._stage_vad_buffer(chunks)

    def _stage_vad_buffer(self, chunks):
        root = Path(self.config.database.path).parent.parent
        epoch = root / 'runtime/reset_epoch'
        if epoch.exists() and chunks[0].timestamp.timestamp() <= float(epoch.read_text()):
            return
        # Combine audio chunks
        groups = [[chunks[0]]]
        for chunk in chunks[1:]:
            previous = groups[-1][-1]
            gap = (chunk.timestamp - previous.timestamp).total_seconds() - previous.duration
            if abs(gap) > 0.025:
                groups.append([])
            groups[-1].append(chunk)
        segments = []
        for group in groups:
            segments.extend(self.continuous.feed(
                np.concatenate([c.audio for c in group]), group[0].timestamp))

        # Stage each segment for batch processing
        for segment in segments:
            try:
                segment_id = self.staging_queue.stage_segment(segment)
                self.stats['vad_segments_detected'] += 1
                self.stats['segments_staged'] += 1
            except Exception as e:
                logger.error(f"Failed to stage segment: {e}")
                self.stats['errors'] += 1

        log_stage("Daemon", f"Processed {len(segments)} VAD segments, now staged for batch")

    def _main_loop(self):
        """Main loop for health checks and stats."""
        last_status_log = time.time()
        status_interval = 300  # Log status every 5 minutes

        while self.is_running and not self._shutdown_requested:
            time.sleep(1)
            self._check_vad_worker()
            self.audio_capture.check_input()
            self.enrollment.tick()
            self.audio_capture.monitor_active = self.monitor.active
            self.monitor.cleanup()
            self.audio_capture.calibration_active = self.enrollment.active
            epoch_path = Path(self.config.database.path).parent.parent / 'runtime/reset_epoch'
            epoch = float(epoch_path.read_text()) if epoch_path.exists() else 0
            if epoch > self._reset_epoch:
                self.continuous.reset()
                for key in ('vad_segments_detected', 'segments_staged', 'batch_jobs_completed', 'captured_chunks', 'errors'):
                    self.stats[key] = 0
                self._reset_epoch = epoch
            from utils.data_lock import write_json
            from zoneinfo import ZoneInfo
            last_audio = self.stats.get('last_delivery_at')
            audio_age = time.time() - datetime.fromisoformat(last_audio).timestamp() if last_audio else time.time() - self.stats['start_time'].timestamp()
            capture_stalled = not self.audio_capture.get_mute_status() and not self.enrollment.active and audio_age > 10
            write_json(Path(self.config.database.path).parent.parent / 'runtime/capture.json', dict(
                {key: value.isoformat() if isinstance(value, datetime) else value for key, value in self.stats.items()}, updated_at=datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(),
                stream_active=bool(self.audio_capture.stream and self.audio_capture.stream.active),
                capture_stalled=capture_stalled,
                vad_worker_alive=bool(self.vad_thread.is_alive()),
                capture_worker_alive=bool(self.audio_capture.process_thread.is_alive()),
                capture_queue_depth=self.audio_capture.chunk_queue.qsize(),
                vad_queue_depth=self.audio_buffer.qsize(),
                input_overflows=self.audio_capture.input_overflows,
                hardware_callbacks=self.audio_capture.hardware_callbacks,
                selected_device=self.audio_capture.selected_device, device_error=self.audio_capture.device_error,
                input_card=self.config.audio.input_card, input_jack_control=self.config.audio.input_jack_control,
                muted=self.audio_capture.get_mute_status(), calibration_active=self.enrollment.active))

            # Periodic status log
            if time.time() - last_status_log > status_interval:
                self._log_status()
                last_status_log = time.time()

        # Shutdown requested
        self.stop()

    def _log_status(self):
        """Log current status."""
        backlog = self.staging_queue.get_backlog_status()

        logger.info(
            f"Status: "
            f"VAD segments={self.stats['vad_segments_detected']}, "
            f"staged={self.stats['segments_staged']}, "
            f"backlog={backlog.get('total_hours', 0):.1f}h, "
            f"errors={self.stats['errors']}"
        )

    def pause(self):
        """Pause processing (but keep audio capture running)."""
        self.is_paused = True
        self.audio_capture.mute()
        logger.info("Pipeline paused")

    def resume(self):
        """Resume processing."""
        self.is_paused = False
        self.audio_capture.unmute()
        logger.info("Pipeline resumed")

    def toggle_pause(self) -> bool:
        """Toggle pause state. Returns True if now paused."""
        if self.is_paused:
            self.resume()
            return False
        else:
            self.pause()
            return True


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Voice Journal Daemon (Batch Mode)")
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to configuration file"
    )
    parser.add_argument(
        "--mute", "-m",
        action="store_true",
        help="Start in muted state"
    )

    args = parser.parse_args()

    # Create daemon
    daemon = VoiceJournalDaemon(config_path=args.config)

    if args.mute:
        daemon.pause()

    # Run
    daemon.start()


if __name__ == "__main__":
    main()
