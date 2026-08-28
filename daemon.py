"""
Main daemon orchestrator for Voice Journal.
Coordinates all 8 stages and manages the pipeline lifecycle.
"""

import signal
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import queue
import os

from config.settings import Config
from audio_capture.capture import AudioCapture
from vad.silero_vad import VADProcessor, SpeechSegment
from speaker_id.identification import SpeakerIdentifier, SpeakerMatch
from asr.transcriber import ASRProcessor, TranscriptSegment
from conversation.grouping import ConversationGrouper, ConversationUnit
from llm_output.classifier import LLMClassifier, ClassificationResult
from obsidian.output import ObsidianWriter
from storage.database import SQLiteStore
from utils.logger import setup_logging, logger, log_stage


class VoiceJournalDaemon:
    """
    Main daemon that orchestrates the voice journal pipeline.
    Runs continuously, processing audio through all 8 stages.
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

        # Initialize all stages
        self._init_stages()

        # Control flags
        self.is_running = False
        self.is_paused = False
        self._shutdown_requested = False

        # Processing queues
        self.audio_queue: queue.Queue = queue.Queue(maxsize=100)
        self.vad_queue: queue.Queue = queue.Queue(maxsize=50)
        self.transcript_queue: queue.Queue = queue.Queue(maxsize=30)

        # Statistics
        self.stats = {
            'segments_processed': 0,
            'conversations_created': 0,
            'errors': 0,
            'start_time': None
        }

        logger.info("VoiceJournalDaemon initialized")

    def _init_stages(self):
        """Initialize all pipeline stages."""
        logger.info("Initializing pipeline stages...")
        # Stage 1: Audio Capture - connected to audio_queue
        self.audio_capture = AudioCapture(
            self.config,
            on_chunk=lambda chunk: self.audio_queue.put(chunk) if not self.is_paused else None
        )

        # Stage 2: VAD
        self.vad_processor = VADProcessor(self.config)

        # Stage 3: Speaker Identification
        self.speaker_identifier = SpeakerIdentifier(self.config)

        # Stage 4: ASR
        self.asr_processor = ASRProcessor(self.config)

        # Stage 5: Conversation Grouping
        self.conversation_grouper = ConversationGrouper(self.config)

        # Stage 6: LLM Classification
        self.llm_classifier = LLMClassifier(self.config)

        # Stage 7: Obsidian Output
        self.obsidian_writer = ObsidianWriter(self.config)

        # Stage 8: SQLite Storage
        self.sqlite_store = SQLiteStore(self.config)

        logger.info("All stages initialized")

    def start(self):
        """Start the daemon."""
        if self.is_running:
            logger.warning("Daemon already running")
            return

        self.is_running = True
        self.stats['start_time'] = datetime.now()

        logger.info("="*60)
        logger.info("Voice Journal Daemon Starting")
        logger.info("="*60)

        # Setup signal handlers
        self._setup_signal_handlers()

        # Start processing threads
        self._start_processing_threads()

        # Start audio capture
        self.audio_capture.start()

        logger.info("Daemon started successfully")

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

        # Stop ASR async processing
        self.asr_processor.stop_async_processing()

        # Flush any pending conversations
        logger.info("Flushing pending conversations...")
        self._flush_pipeline()

        # Wait for threads
        self._stop_processing_threads()

        logger.info("="*60)
        logger.info("Voice Journal Daemon Stopped")
        logger.info(f"Stats: {self.stats}")
        logger.info("="*60)

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

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        self._shutdown_requested = True

    def _start_processing_threads(self):
        """Start all processing threads."""
        self.threads = {}

        # VAD processing thread
        self.threads['vad'] = threading.Thread(
            target=self._vad_worker,
            daemon=True,
            name="VADWorker"
        )

        # ASR processing thread
        self.threads['asr'] = threading.Thread(
            target=self._asr_worker,
            daemon=True,
            name="ASRWorker"
        )

        # Conversation grouping thread
        self.threads['conversation'] = threading.Thread(
            target=self._conversation_worker,
            daemon=True,
            name="ConversationWorker"
        )

        # Start all threads
        for name, thread in self.threads.items():
            thread.start()
            logger.info(f"Started {name} thread")

    def _stop_processing_threads(self):
        """Stop all processing threads."""
        # Send stop signals
        self.audio_queue.put(None)
        self.vad_queue.put(None)
        self.transcript_queue.put(None)

        # Wait for threads to finish
        for name, thread in self.threads.items():
            thread.join(timeout=5)
            logger.info(f"Stopped {name} thread")

    def _main_loop(self):
        """Main loop for health checks and stats."""
        import time

        last_health_check = time.time()
        health_interval = self.config.daemon.health_check_interval

        while self.is_running and not self._shutdown_requested:
            time.sleep(1)

            # Health check
            if time.time() - last_health_check > health_interval:
                self._health_check()
                last_health_check = time.time()

        # Shutdown requested
        self.stop()

    def _health_check(self):
        """Perform health check on all stages."""
        # Check Ollama availability
        from llm_output.classifier import check_ollama_model

        ollama_ok = check_ollama_model(
            self.config.llm.model,
            self.config.llm.ollama_host
        )

        if not ollama_ok:
            logger.warning("Ollama model not available")

        # Log stats
        logger.info(
            f"Health check: segments={self.stats['segments_processed']}, "
            f"conversations={self.stats['conversations_created']}, "
            f"errors={self.stats['errors']}, "
            f"queues: audio={self.audio_queue.qsize()}, "
            f"vad={self.vad_queue.qsize()}, trans={self.transcript_queue.qsize()}"
        )

    def _vad_worker(self):
        """Worker thread for VAD processing."""
        from audio_capture.capture import AudioChunk

        audio_buffer = []
        buffer_duration = 0.0
        buffer_max = 1800.0  # Process every 30 minutes of audio (was 10 minutes)

        while self.is_running and not self._shutdown_requested:
            try:
                chunk = self.audio_queue.get(timeout=1.0)
                if chunk is None:
                    break

                if self.is_paused:
                    continue

                # Accumulate audio
                audio_buffer.append(chunk)
                buffer_duration += chunk.duration

                # Log progress every 5 minutes
                if int(buffer_duration) % 300 == 0 and int(buffer_duration) > 0:
                    minutes = int(buffer_duration) // 60
                    logger.info(f"Buffering: {minutes}/30 minutes before processing...")

                # Process when buffer is full (30 minutes)
                if buffer_duration >= buffer_max:
                    logger.info(f"Processing 30-minute segment ({buffer_duration:.1f}s of audio)...")
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
        """Process buffered audio chunks with VAD."""
        import numpy as np

        # Combine audio chunks
        audio_data = np.concatenate([c.audio for c in chunks])
        reference_time = chunks[0].timestamp

        # VAD processing
        segments = self.vad_processor.process_audio_chunk(audio_data, reference_time)

        # Queue for ASR
        for segment in segments:
            self.vad_queue.put(segment)
            self.stats['segments_processed'] += 1

    def _asr_worker(self):
        """Worker thread for ASR and speaker ID."""
        while self.is_running and not self._shutdown_requested:
            try:
                segment = self.vad_queue.get(timeout=1.0)
                if segment is None:
                    break

                if self.is_paused:
                    continue

                # Speaker identification
                speaker_match = self.speaker_identifier.identify_speaker(segment)

                # Transcription
                transcript = self.asr_processor.transcribe_with_timing(
                    segment,
                    speaker_match,
                    self.stats['segments_processed']
                )

                if transcript:
                    self.transcript_queue.put(transcript)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"ASR worker error: {e}")
                self.stats['errors'] += 1

    def _conversation_worker(self):
        """Worker thread for conversation grouping and output."""
        while self.is_running and not self._shutdown_requested:
            try:
                transcript = self.transcript_queue.get(timeout=5.0)
                if transcript is None:
                    break

                if self.is_paused:
                    continue

                # Add to conversation grouper
                conversation = self.conversation_grouper.add_segment(transcript)

                # If conversation is complete, process it
                if conversation:
                    self._process_conversation(conversation)

            except queue.Empty:
                # Check for timeout-based conversation completion
                pass
            except Exception as e:
                logger.error(f"Conversation worker error: {e}")
                self.stats['errors'] += 1

    def _process_conversation(self, conversation: ConversationUnit):
        """Process a complete conversation through remaining stages."""
        try:
            # Stage 6: LLM Classification
            classification = self.llm_classifier.classify(conversation)

            # Stage 7: Write to Obsidian
            note_path = self.obsidian_writer.write_conversation_note(
                conversation,
                classification
            )

            # Stage 8: Store in SQLite
            self.sqlite_store.insert_conversation(
                conversation,
                classification,
                note_path
            )

            self.stats['conversations_created'] += 1

            logger.info(
                f"Conversation #{conversation.conversation_id} processed: "
                f"{classification.source_type}, {conversation.total_word_count} words"
            )

        except Exception as e:
            logger.error(f"Error processing conversation: {e}")
            self.stats['errors'] += 1

    def _flush_pipeline(self):
        """Flush any pending data in the pipeline."""
        # Flush conversation grouper
        conversation = self.conversation_grouper.flush()

        while conversation:
            self._process_conversation(conversation)
            conversation = self.conversation_grouper.flush()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Voice Journal Daemon")
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
