"""
Stage 4: Automatic Speech Recognition using faster-whisper.
Transcribes speech segments with language auto-detection.
"""

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Iterator, Tuple
import queue
import threading
import warnings

import numpy as np

from config.settings import Config
from vad.silero_vad import SpeechSegment
from speaker_id.identification import SpeakerMatch
from utils.logger import logger, log_stage, log_metric


@dataclass
class TranscriptSegment:
    """A transcribed speech segment with metadata."""
    text: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    language: str
    language_probability: float
    speaker: str
    speaker_confidence: float
    words: List[dict]  # Word-level timestamps if available
    segmentation_id: int

    @property
    def word_count(self) -> int:
        return len([w for w in self.words if w.get('word', '').strip()])


class ASRProcessor:
    """
    Stage 4: Speech-to-text processing using faster-whisper.
    Optimized for CPU inference with CTranslate2 backend.
    """

    def __init__(self, config: Config):
        self.config = config

        # Import faster-whisper here to allow graceful fallback
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "faster-whisper is required. Install with: pip install faster-whisper"
            )

        # Initialize model
        logger.info(f"Loading Whisper model: {config.asr.model_size} ({config.asr.compute_type})")

        self.model = WhisperModel(
            config.asr.model_size,
            device=config.asr.device,
            compute_type=config.asr.compute_type
        )

        # Get actual model info
        self.model_info = {
            "size": config.asr.model_size,
            "compute_type": config.asr.compute_type,
            "device": config.asr.device,
            "language": config.asr.language or "auto"
        }

        logger.info(f"Whisper model loaded: {self.model_info}")

        # Processing queue for async transcription
        self.transcription_queue: queue.Queue = queue.Queue()
        self.result_queue: queue.Queue = queue.Queue()
        self.is_running = False

    def transcribe_segment(
        self,
        audio: np.ndarray,
        speaker_match: SpeakerMatch,
        segment_id: int = 0
    ) -> Optional[TranscriptSegment]:
        """
        Transcribe a single audio segment.

        Args:
            audio: Audio data as float32 array
            speaker_match: Speaker identification result
            segment_id: ID for this segment

        Returns:
            TranscriptSegment or None if transcription fails
        """
        start_time = time.time()

        # Ensure correct format
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        if audio.ndim == 2:
            audio = audio[:, 0]  # Mono

        try:
            # Transcribe with faster-whisper
            segments, info = self.model.transcribe(
                audio,
                language=self.config.asr.language,
                beam_size=self.config.asr.beam_size,
                vad_filter=self.config.asr.vad_filter,
                temperature=0.0,  # Deterministic for consistency
                condition_on_previous_text=False,  # Each segment is independent
            )

            # Check if segments is None or not iterable
            if segments is None:
                log_stage("ASR", f"No segments returned for segment {segment_id}")
                return None

            # Collect transcript
            transcript_parts = []
            word_list = []

            # Convert generator to list to handle iteration safely
            try:
                segments_list = list(segments)
            except TypeError:
                # If it's not iterable, return None
                log_stage("ASR", f"Segments not iterable for segment {segment_id}")
                return None

            for seg in segments_list:
                if seg is None:
                    continue
                transcript_parts.append(seg.text if hasattr(seg, 'text') else '')
                # Collect word-level info if available
                if hasattr(seg, 'words') and seg.words:
                    for word in seg.words:
                        if word:
                            word_list.append({
                                "word": getattr(word, 'word', ''),
                                "start": getattr(word, 'start', 0.0),
                                "end": getattr(word, 'end', 0.0),
                                "probability": getattr(word, 'probability', 1.0)
                            })

            # Combine transcript
            text = " ".join(transcript_parts).strip()

            if not text:
                log_stage("ASR", f"Empty transcript for segment {segment_id}")
                return None

            duration = len(audio) / 16000  # Assuming 16kHz

            log_metric("ASR", "transcription_time", time.time() - start_time, "s")
            log_metric("ASR", "real_time_factor", (time.time() - start_time) / duration if duration > 0 else 0)
            log_stage("ASR", f"[{info.language}] {text[:50]}...")

            return TranscriptSegment(
                text=text,
                start_time=datetime.now(),  # Will be replaced with actual segment time
                end_time=datetime.now(),
                duration_seconds=duration,
                language=info.language,
                language_probability=info.language_probability,
                speaker=speaker_match.speaker,
                speaker_confidence=speaker_match.confidence,
                words=word_list,
                segmentation_id=segment_id
            )

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None

    def transcribe_with_timing(
        self,
        segment: SpeechSegment,
        speaker_match: SpeakerMatch,
        segment_id: int = 0
    ) -> Optional[TranscriptSegment]:
        """
        Transcribe a speech segment with proper timing from VAD segment.
        """
        result = self.transcribe_segment(segment.audio, speaker_match, segment_id)

        if result:
            # Update timing from VAD segment
            result.start_time = segment.start_time
            result.end_time = segment.end_time
            result.duration_seconds = segment.duration_seconds

        return result

    def batch_transcribe(
        self,
        segments: List[Tuple[SpeechSegment, SpeakerMatch]]
    ) -> List[TranscriptSegment]:
        """
        Transcribe multiple segments sequentially.
        """
        results = []
        for i, (segment, speaker_match) in enumerate(segments):
            result = self.transcribe_with_timing(segment, speaker_match, i)
            if result:
                results.append(result)
        return results

    def start_async_processing(self):
        """Start the background transcription worker."""
        if self.is_running:
            return

        self.is_running = True
        self.worker_thread = threading.Thread(target=self._transcription_worker, daemon=True)
        self.worker_thread.start()
        log_stage("ASR", "Async processor started")

    def stop_async_processing(self):
        """Stop the background worker."""
        self.is_running = False
        self.transcription_queue.put(None)  # Signal to stop
        if hasattr(self, 'worker_thread'):
            self.worker_thread.join(timeout=5)
        log_stage("ASR", "Async processor stopped")

    def _transcription_worker(self):
        """Background worker for transcription."""
        while self.is_running:
            try:
                item = self.transcription_queue.get(timeout=1)
                if item is None:
                    break

                segment, speaker_match, segment_id = item
                result = self.transcribe_with_timing(segment, speaker_match, segment_id)
                self.result_queue.put(result)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Transcription worker error: {e}")

    def queue_for_transcription(
        self,
        segment: SpeechSegment,
        speaker_match: SpeakerMatch,
        segment_id: int
    ):
        """Add segment to the transcription queue."""
        self.transcription_queue.put((segment, speaker_match, segment_id))

    def get_transcription_result(self, timeout: float = 30.0) -> Optional[TranscriptSegment]:
        """Get a transcription result from the queue."""
        try:
            return self.result_queue.get(timeout=timeout)
        except queue.Empty:
            return None


def test_asr(audio_path: str, config_path: str = None):
    """Test ASR on an audio file."""
    from config.settings import Config
    from vad.silero_vad import VADProcessor
    from speaker_id.identification import SpeakerIdentifier
    from datetime import datetime

    print(f"\nTesting ASR on: {audio_path}")

    # Load config
    if config_path:
        config = Config.from_yaml(config_path)
    else:
        config = Config()

    # Initialize processors
    vad_processor = VADProcessor(config)
    speaker_id = SpeakerIdentifier(config)
    asr = ASRProcessor(config)

    # Load audio
    import librosa
    audio, sr = librosa.load(audio_path, sr=16000, mono=True)

    # Get speech segments
    segments = vad_processor.process_audio_chunk(audio, datetime.now())
    print(f"\nFound {len(segments)} speech segments")

    # Identify speakers and transcribe
    for i, segment in enumerate(segments, 1):
        speaker_match = speaker_id.identify_speaker(segment)
        transcript = asr.transcribe_with_timing(segment, speaker_match, i)

        if transcript:
            print(f"\n[Segment {i}] {segment.duration_seconds:.2f}s")
            print(f"  Speaker: {transcript.speaker} ({transcript.speaker_confidence:.2f})")
            print(f"  Language: {transcript.language} ({transcript.language_probability:.2f})")
            print(f"  Text: {transcript.text}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_asr(sys.argv[1])
    else:
        print("Usage: python -m voice_journal.asr <audio_file>")
