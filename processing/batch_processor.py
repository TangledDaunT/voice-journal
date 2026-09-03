"""
Batch Processing Module.
Orchestrates deferred processing of all stages after VAD.
Runs as a scheduled batch job, not in real-time.
"""

import os
import json
import time
import shutil
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict, field
import sqlite3
import psutil

from config.settings import Config
from vad.silero_vad import SpeechSegment
from vad.segment_merger import SegmentMerger, MergedSegment
from audio_capture.preprocess import AudioPreprocessor
from asr.transcriber_batch import BatchASRProcessor  # New batch-optimized transcriber
from speaker_id.identification import SpeakerIdentifier
from conversation.grouping import ConversationGrouper, ConversationUnit
from llm_output.classifier import LLMClassifier
from obsidian.output import ObsidianWriter
from storage.database import SQLiteStore, BacklogTracker
from utils.logger import logger, log_stage, log_metric


@dataclass
class StagedSegment:
    """A segment staged for batch processing."""
    segment_id: str
    start_time: datetime
    end_time: datetime
    audio_path: str  # Path to saved audio file
    sample_rate: int
    duration_seconds: float
    captured_at: datetime
    processing_attempts: int = 0
    last_error: Optional[str] = None


@dataclass
class BatchJobConfig:
    """Configuration for a batch processing job."""
    job_id: str
    started_at: datetime
    use_fallback_model: bool = False
    segments_to_process: int = 0


class StagingQueue:
    """
    Manages the staging queue for VAD segments awaiting batch processing.
    Stores raw audio + metadata on disk, tracks backlog in SQLite.
    """

    def __init__(self, config: Config, disable_denoising: bool = False):
        if disable_denoising:
            config = config.model_copy(deep=True)
            config.preprocessing.enable_denoising = False
        self.config = config
        self.staging_dir = Path(config.audio.audio_storage_path) / "staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        # Backlog tracker in SQLite
        self.backlog_tracker = BacklogTracker(config)

        logger.info(f"StagingQueue initialized at: {self.staging_dir}")

    def stage_segment(self, segment: SpeechSegment) -> str:
        """
        Stage a VAD segment for batch processing.

        Returns:
            segment_id for tracking
        """
        # Generate unique ID
        segment_id = f"{segment.start_time.strftime('%Y%m%d_%H%M%S')}_{id(segment)}"
        segment_id = segment_id.replace(" ", "_").replace(":", "-")

        # Save audio
        audio_filename = f"{segment_id}.npy"
        audio_path = self.staging_dir / audio_filename

        np.save(str(audio_path), segment.audio)

        # Save metadata
        metadata_path = self.staging_dir / f"{segment_id}.json"
        metadata = {
            "segment_id": segment_id,
            "start_time": segment.start_time.isoformat(),
            "end_time": segment.end_time.isoformat(),
            "audio_path": str(audio_path),
            "sample_rate": segment.sample_rate,
            "duration_seconds": segment.duration_seconds,
            "captured_at": datetime.now().isoformat()
        }

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Track in backlog
        self.backlog_tracker.add_segment(
            segment_id=segment_id,
            duration_seconds=segment.duration_seconds
        )

        log_stage("Staging", f"Segment staged: {segment.duration_seconds:.2f}s")
        return segment_id

    def get_pending_segments(self, limit: int = None) -> List[StagedSegment]:
        """Get all pending segments from staging."""
        segments = []

        for json_file in sorted(self.staging_dir.glob("*.json")):
            try:
                with open(json_file, "r") as f:
                    metadata = json.load(f)

                segment = StagedSegment(
                    segment_id=metadata["segment_id"],
                    start_time=datetime.fromisoformat(metadata["start_time"]),
                    end_time=datetime.fromisoformat(metadata["end_time"]),
                    audio_path=metadata["audio_path"],
                    sample_rate=metadata["sample_rate"],
                    duration_seconds=metadata["duration_seconds"],
                    captured_at=datetime.fromisoformat(metadata["captured_at"])
                )
                segments.append(segment)
            except Exception as e:
                logger.error(f"Failed to load segment {json_file}: {e}")
                continue

        # Sort by capture time (oldest first)
        segments.sort(key=lambda s: s.captured_at)

        if limit:
            segments = segments[:limit]

        return segments

    def load_segment_audio(self, segment: StagedSegment) -> SpeechSegment:
        """Load audio for a staged segment."""
        audio = np.load(segment.audio_path)

        return SpeechSegment(
            start_time=segment.start_time,
            end_time=segment.end_time,
            audio=audio,
            sample_rate=segment.sample_rate
        )

    def mark_processed(self, segment_id: str):
        """Mark a segment as processed (delete staged files)."""
        # Delete audio and metadata files
        audio_path = self.staging_dir / f"{segment_id}.npy"
        metadata_path = self.staging_dir / f"{segment_id}.json"

        for path in [audio_path, metadata_path]:
            if path.exists():
                path.unlink()

        # Update backlog
        self.backlog_tracker.remove_segment(segment_id)

        log_stage("Staging", f"Segment processed: {segment_id}")

    def get_backlog_status(self) -> Dict[str, Any]:
        """Get current backlog status."""
        return self.backlog_tracker.get_status()


class BatchProcessor:
    """
    Processes staged VAD segments in batch.
    Runs the full pipeline (merge → preprocess → ASR → speaker ID → grouping → LLM → output).
    """

    def __init__(self, config: Config):
        self.config = config

        # Components
        self.staging_queue = StagingQueue(config)
        self.segment_merger = SegmentMerger(config)
        self.preprocessor = AudioPreprocessor(config)

        # Will be initialized lazily (heavy models)
        self._asr_processor = None
        self._fallback_asr = None
        self._speaker_identifier = None
        self._conversation_grouper = None
        self._llm_classifier = None
        self._obsidian_writer = None
        self._sqlite_store = None

        self.is_running = False

        logger.info("BatchProcessor initialized")

    def _init_heavy_components(self, use_fallback: bool = False):
        """Initialize heavy model components lazily."""
        if use_fallback:
            # Use fallback model for overflow
            if self._fallback_asr is None:
                logger.info("Loading fallback ASR model...")
                fallback_config = self.config.model_copy()
                fallback_config.asr.model_size = self.config.scheduler.fallback_model
                fallback_config.asr.compute_type = self.config.scheduler.fallback_compute_type
                self._fallback_asr = BatchASRProcessor(fallback_config)
        else:
            # Use primary model
            if self._asr_processor is None:
                logger.info("Loading primary ASR model...")
                self._asr_processor = BatchASRProcessor(self.config)

        if self._speaker_identifier is None:
            self._speaker_identifier = SpeakerIdentifier(self.config)

        if self._conversation_grouper is None:
            self._conversation_grouper = ConversationGrouper(self.config)

        if self._llm_classifier is None:
            self._llm_classifier = LLMClassifier(self.config)

        if self._obsidian_writer is None:
            self._obsidian_writer = ObsidianWriter(self.config)

        if self._sqlite_store is None:
            self._sqlite_store = SQLiteStore(self.config)

    def run_batch(
        self,
        use_fallback: bool = False,
        max_segments: int = None
    ) -> Dict[str, Any]:
        """
        Run a batch processing job.

        Args:
            use_fallback: If True, use fallback model (for overflow)
            max_segments: Maximum segments to process in this batch

        Returns:
            Job statistics
        """
        job_start = datetime.now()
        job_id = job_start.strftime("%Y%m%d_%H%M%S")

        log_stage("Batch", f"Starting batch job {job_id}")
        log_stage("Batch", f"Using fallback: {use_fallback}")

        # Initialize components
        self._init_heavy_components(use_fallback)

        # Get pending segments
        pending = self.staging_queue.get_pending_segments(limit=max_segments)

        if not pending:
            log_stage("Batch", "No pending segments")
            return {
                "job_id": job_id,
                "segments_processed": 0,
                "conversations_created": 0,
                "errors": 0
            }

        # Load audio for all segments
        log_stage("Batch", f"Loading {len(pending)} segments...")
        vad_segments = []
        for staged in pending:
            try:
                vad_seg = self.staging_queue.load_segment_audio(staged)
                vad_seg.segment_id = staged.segment_id  # Keep ID for tracking (FIXED typo)
                vad_segments.append(vad_seg)
            except Exception as e:
                logger.error(f"Failed to load segment {staged.segment_id}: {e}")
                continue

        if not vad_segments:
            return {
                "job_id": job_id,
                "segments_processed": 0,
                "conversations_created": 0,
                "errors": len(pending)
            }

        # Merge segments into transcription units
        log_stage("Batch", "Merging segments...")
        merged_units = self.segment_merger.add_segments_batch(vad_segments)

        # Preprocess
        log_stage("Batch", "Preprocessing audio...")
        original_rms_by_unit = []
        for unit in merged_units:
            preprocessed = self.preprocessor.preprocess(unit.audio, unit.sample_rate)
            unit.audio = preprocessed.audio
            original_rms_by_unit.append(preprocessed.original_rms_db)

        # Choose ASR processor
        asr = self._fallback_asr if use_fallback else self._asr_processor

        # Transcribe
        log_stage("Batch", f"Transcribing {len(merged_units)} units...")
        transcript_segments = []
        audio_by_transcript_id = {}

        for i, unit in enumerate(merged_units, 1):
            try:
                original_rms_db = original_rms_by_unit[i - 1]
                if original_rms_db < self.config.preprocessing.min_rms_db_for_asr:
                    for source_seg in unit.source_segments:
                        if hasattr(source_seg, 'segment_id'):
                            self.staging_queue.mark_processed(source_seg.segment_id)
                    log_stage(
                        "ASR",
                        f"Skipped low-energy unit {i}: "
                        f"rms={original_rms_db:.1f}dB, "
                        f"threshold={self.config.preprocessing.min_rms_db_for_asr:.1f}dB"
                    )
                    continue

                # Transcribe
                result = asr.transcribe_merged_segment(unit)

                if result:
                    # Map back to source segment IDs
                    for source_seg in unit.source_segments:
                        if hasattr(source_seg, 'segment_id'):
                            self.staging_queue.mark_processed(source_seg.segment_id)

                    transcript_segments.append(result)
                    audio_by_transcript_id[id(result)] = (unit.audio.copy(), unit.sample_rate)
                    log_stage("Batch", f"[{i}/{len(merged_units)}] {unit.duration_seconds:.1f}s → {result.word_count} words")

            except Exception as e:
                logger.error(f"Transcription error for unit {i}: {e}")
                continue

        # Group into conversations
        log_stage("Batch", "Grouping conversations...")
        conversations = self._conversation_grouper.group_segments(transcript_segments)

        # Process each conversation (LLM + output)
        conversations_created = 0
        errors = 0

        for conversation in conversations:
            try:
                # Cleanup is optional and never replaces the raw ASR transcript.
                cleanup = self._llm_classifier.cleanup(conversation)

                # Classify the readable version while retaining raw text for storage.
                classification = self._llm_classifier.classify(
                    conversation,
                    transcript=cleanup.cleaned_transcript
                )

                self._cache_conversation_audio(conversation, audio_by_transcript_id)

                # Write to Obsidian
                note_path = self._obsidian_writer.write_conversation_note(
                    conversation,
                    classification,
                    cleaned_transcript=cleanup.cleaned_transcript
                )

                # Store in SQLite
                self._sqlite_store.insert_conversation(
                    conversation,
                    classification,
                    note_path,
                    raw_transcript=cleanup.raw_transcript,
                    cleaned_transcript=cleanup.cleaned_transcript
                )

                conversations_created += 1
                log_stage("Batch", f"Conversation {conversation.conversation_id}: {classification.source_type}")

            except Exception as e:
                logger.error(f"Error processing conversation: {e}")
                errors += 1

        # Job complete
        job_end = datetime.now()
        duration = (job_end - job_start).total_seconds()

        stats = {
            "job_id": job_id,
            "segments_processed": len(pending),
            "transcription_units": len(merged_units),
            "conversations_created": conversations_created,
            "errors": errors,
            "duration_seconds": duration,
            "used_fallback": use_fallback
        }

        log_stage("Batch", f"Job complete: {conversations_created} conversations in {duration:.1f}s")

        return stats

    def _cache_conversation_audio(self, conversation, audio_by_transcript_id):
        """Cache the preprocessed audio represented by a conversation as Opus."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.warning("Audio cache skipped: ffmpeg is not installed")
            return

        audio_parts = [
            audio_by_transcript_id[id(segment)][0]
            for segment in conversation.transcript_segments
            if id(segment) in audio_by_transcript_id
        ]
        if not audio_parts:
            return

        sample_rate = audio_by_transcript_id[id(conversation.transcript_segments[0])][1]
        date_dir = Path(self.config.dashboard.audio_cache_path) / conversation.start_time.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        output_path = date_dir / f"{conversation.start_time.strftime('%H%M')}-{conversation.conversation_id}.ogg"
        audio = np.concatenate(audio_parts).astype(np.float32)
        try:
            subprocess.run(
                [ffmpeg, "-y", "-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
                 "-c:a", "libopus", "-b:a", f"{self.config.dashboard.audio_bitrate_kbps}k", str(output_path)],
                input=audio.tobytes(), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
            log_stage("AudioCache", f"Cached conversation audio: {output_path}")
        except (OSError, subprocess.CalledProcessError) as exc:
            logger.warning(f"Audio cache failed for conversation {conversation.conversation_id}: {exc}")

        cutoff = time.time() - self.config.dashboard.audio_retention_days * 86400
        for cached_file in Path(self.config.dashboard.audio_cache_path).rglob("*.ogg"):
            if cached_file.stat().st_mtime < cutoff:
                cached_file.unlink(missing_ok=True)


class BatchScheduler:
    """
    Schedules batch processing based on system load.
    Runs batch jobs when CPU is idle, with guaranteed overnight window.
    """

    def __init__(self, config: Config, batch_processor: BatchProcessor):
        self.config = config
        self.scheduler_config = config.scheduler
        self.batch_processor = batch_processor

        # Idle detection state
        self.idle_start_time: Optional[datetime] = None
        self.is_processing = False

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        logger.info("BatchScheduler initialized")

    def start(self):
        """Start the scheduler loop."""
        if self._thread and self._thread.is_alive():
            logger.warning("Scheduler already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()

        log_stage("Scheduler", "Started")

    def stop(self):
        """Stop the scheduler."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

        log_stage("Scheduler", "Stopped")

    def _scheduler_loop(self):
        """Main scheduler loop."""
        check_interval = self.scheduler_config.idle_check_interval

        while not self._stop_event.is_set():
            try:
                self._check_and_run()
                time.sleep(check_interval)

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(60)

    def _check_and_run(self):
        """Check conditions and run batch processing if appropriate."""
        # Guard: Don't start a new batch if one is already running
        if self.is_processing:
            logger.debug("Batch already in progress, skipping scheduler check")
            return

        now = datetime.now()
        current_hour = now.hour

        # Check if in guaranteed processing window
        guaranteed_window = self._in_guaranteed_window(current_hour)

        # Check if CPU is idle (sample once, non-blocking during batch)
        cpu_idle = self._check_cpu_idle()

        # Check backlog
        backlog_status = self.batch_processor.staging_queue.get_backlog_status()
        backlog_hours = backlog_status.get("total_hours", 0.0)

        # Determine if we should run
        should_run = False
        reason = ""

        if guaranteed_window:
            # Overnight: run regardless of CPU, process larger batches
            should_run = True
            reason = "guaranteed window (overnight)"

        elif cpu_idle and self.idle_start_time:
            idle_duration = (now - self.idle_start_time).total_seconds()
            if idle_duration >= self.scheduler_config.min_idle_duration_seconds:
                should_run = True
                reason = f"CPU idle for {idle_duration:.0f}s (daytime)"

        if should_run and backlog_hours > 0:
            # Determine batch size based on time of day
            # Daytime: small chunks, re-check idle between batches
            # Overnight: larger chunks, run more aggressively
            if guaranteed_window:
                # Overnight: process larger batches (full-CPU is fine)
                max_audio_hours = self.scheduler_config.overnight_batch_hours
            else:
                # Daytime: small chunks so we back off quickly if user returns
                max_audio_hours = self.scheduler_config.daytime_batch_hours

            # Convert to segment count (assume avg 10s per VAD segment)
            # This is approximate; actual segments vary
            max_segments = int(max_audio_hours * 3600 / 10)

            # Determine if using fallback model
            use_fallback = backlog_hours >= self.scheduler_config.backlog_overflow_hours

            log_stage(
                "Scheduler",
                f"Starting batch: {reason}, backlog={backlog_hours:.1f}h, "
                f"chunk={max_audio_hours:.1f}h, fallback={use_fallback}"
            )

            try:
                self.is_processing = True
                # Run BOUNDED batch - will return after processing chunk
                # Scheduler loop will re-check idle before starting next chunk
                self.batch_processor.run_batch(
                    use_fallback=use_fallback,
                    max_segments=max_segments
                )
            finally:
                self.is_processing = False
                # For daytime: reset idle timer so we re-check before next batch
                # For overnight: keep going (scheduler will immediately trigger again)
                if not guaranteed_window:
                    self.idle_start_time = None

    def _in_guaranteed_window(self, current_hour: int) -> bool:
        """Check if we're in the guaranteed processing window."""
        if not self.scheduler_config.guaranteed_window_enabled:
            return False

        start = self.scheduler_config.guaranteed_window_start_hour
        end = self.scheduler_config.guaranteed_window_end_hour

        # Handle overnight window (e.g., 22:00 to 06:00)
        if start > end:
            return current_hour >= start or current_hour < end
        else:
            return start <= current_hour < end

    def _check_cpu_idle(self) -> bool:
        """Check if CPU is below idle threshold."""
        try:
            # Get CPU usage over last 1 second
            cpu_percent = psutil.cpu_percent(interval=1.0)

            threshold = self.scheduler_config.cpu_idle_threshold

            if cpu_percent < threshold:
                if self.idle_start_time is None:
                    self.idle_start_time = datetime.now()
                return True
            else:
                self.idle_start_time = None
                return False

        except Exception as e:
            logger.error(f"Failed to check CPU: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status."""
        backlog = self.batch_processor.staging_queue.get_backlog_status()

        return {
            "scheduler_running": self._thread.is_alive() if self._thread else False,
            "currently_processing": self.is_processing,
            "backlog_hours": backlog.get("total_hours", 0.0),
            "backlog_segments": backlog.get("segment_count", 0),
            "last_updated": datetime.now().isoformat(),
            "in_guaranteed_window": self._in_guaranteed_window(datetime.now().hour),
            "cpu_idle": self.idle_start_time is not None,
            "idle_since": self.idle_start_time.isoformat() if self.idle_start_time else None
        }


# CLI for manual batch processing
def run_batch_job(
    config_path: str = None,
    use_fallback: bool = False,
    disable_denoising: bool = False
):
    """Run a batch job manually (CLI entry point)."""
    if config_path:
        config = Config.from_yaml(config_path)
    else:
        config = Config()

    processor = BatchProcessor(config, disable_denoising=disable_denoising)
    stats = processor.run_batch(use_fallback=use_fallback)

    print("\nBatch job complete:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run batch processing")
    parser.add_argument("--config", "-c", help="Path to config file")
    parser.add_argument("--fallback", action="store_true", help="Use fallback model")
    parser.add_argument(
        "--no-denoise",
        action="store_true",
        help="Disable denoising for this batch only (diagnostic A/B test)",
    )
    args = parser.parse_args()

    run_batch_job(
        config_path=args.config,
        use_fallback=args.fallback,
        disable_denoising=args.no_denoise,
    )
