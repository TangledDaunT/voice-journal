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
        self.staging_queue = StagingQueue(self.config)

        self.audio_capture = AudioCapture(
            self.config,
            on_chunk=self._handle_audio_chunk
        )

        # Stage 2: VAD (lightweight)
        self.vad_processor = VADProcessor(self.config)

        # Audio buffer for VAD
        self.audio_buffer: queue.Queue = queue.Queue(maxsize=100)

        logger.info("Real-time components initialized")

    def _init_batch_components(self):
        """Initialize batch processing components."""
        logger.info("Initializing batch components...")

        # Batch processor
        self.batch_processor = BatchProcessor(self.config)

        # Scheduler
        self.batch_scheduler = BatchScheduler(self.config, self.batch_processor)

        logger.info("Batch components initialized")

    def _handle_audio_chunk(self, chunk):
        """Handle incoming audio chunk from capture."""
        if not self.is_paused:
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
        buffer_max = 1800.0  # Process every 30 minutes

        while self.is_running and not self._shutdown_requested:
            try:
                chunk = self.audio_buffer.get(timeout=1.0)
                if chunk is None:
                    break

                if self.is_paused:
                    continue

                # Accumulate audio
                audio_buffer.append(chunk)
                buffer_duration += chunk.duration

                # Process when buffer is full
                if buffer_duration >= buffer_max:
                    self._process_vad_buffer(audio_buffer)
                    audio_buffer = []
                    buffer_duration = 0.0

            except queue.Empty:
                # Process remaining buffer periodically
                if audio_buffer:
                    self._process_vad_buffer(audio_buffer)
                    audio_buffer = []
                    buffer_duration = 0.0

            except Exception as e:
                logger.error(f"VAD worker error: {e}")
                self.stats['errors'] += 1

    def _process_vad_buffer(self, chunks: list):
        """Process buffered audio chunks with VAD and stage for batch."""
        import numpy as np

        # Combine audio chunks
        audio_data = np.concatenate([c.audio for c in chunks])
        reference_time = chunks[0].timestamp

        # VAD processing
        segments = self.vad_processor.process_audio_chunk(audio_data, reference_time)

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
