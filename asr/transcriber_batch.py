"""
Batch ASR Processor (Fix 3 & 4).
Transcribes merged segments using a configurable faster-whisper model with confidence gating.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import numpy as np

from config.settings import Config
from vad.segment_merger import MergedSegment
from utils.logger import logger, log_stage, log_metric


@dataclass
class ConfidenceMetrics:
    """Confidence metrics for a transcribed segment."""
    no_speech_prob: float
    avg_logprob: float
    compression_ratio: Optional[float] = None

    @property
    def is_low_confidence(self) -> bool:
        """Check if this segment has low confidence."""
        # These thresholds are updated by config
        return (
            self.no_speech_prob > 0.6 or
            self.avg_logprob < -1.0
        )


@dataclass
class TranscriptSegmentWithConfidence:
    """Transcript segment with confidence metrics and metadata."""
    # Core transcript
    text: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float

    # Language
    language: str
    language_probability: float

    # Speaker (from speaker ID upstream)
    speaker: str
    speaker_confidence: float

    # Word-level timestamps
    words: List[dict] = field(default_factory=list)

    # Confidence metrics (NEW)
    confidence_metrics: Optional[ConfidenceMetrics] = None
    low_confidence: bool = False

    # Source tracking
    merge_count: int = 1
    source_segments: int = 1

    @property
    def word_count(self) -> int:
        return len([w for w in self.words if w.get("word", "").strip()])

    def format_for_obsidian(self) -> str:
        """Format transcript for Obsidian with confidence marker if needed."""
        timestamp = self.start_time.strftime("%H:%M:%S")
        speaker = self.speaker.capitalize()

        # Add confidence marker
        marker = " ⚠️" if self.low_confidence else ""

        return f"[{timestamp}] {speaker}: {self.text}{marker}"


class BatchASRProcessor:
    """
    Batch-oriented ASR processor with:
    - Configurable faster-whisper model for accuracy
    - Anti-hallucination settings
    - Confidence gating and flagging
    """

    def __init__(self, config: Config):
        self.config = config
        self.asr_config = config.asr

        # Model settings
        self.model_size = self.asr_config.model_size
        self.compute_type = self.asr_config.compute_type
        self.device = self.asr_config.device

        # Anti-hallucination settings
        self.vad_filter = self.asr_config.vad_filter
        self.condition_on_previous_text = self.asr_config.condition_on_previous_text
        self.beam_size = self.asr_config.beam_size
        self.initial_prompt = self.asr_config.initial_prompt

        # Confidence thresholds
        self.no_speech_prob_threshold = self.asr_config.no_speech_prob_threshold
        self.avg_logprob_threshold = self.asr_config.avg_logprob_threshold

        # Initialize model
        self._init_model()

        self.stats = {
            "segments_transcribed": 0,
            "low_confidence_flagged": 0,
            "total_words": 0
        }

        logger.info(
            f"BatchASRProcessor initialized: "
            f"model={self.model_size}, "
            f"compute={self.compute_type}, "
            f"vad_filter={self.vad_filter}, "
            f"condition_on_previous={self.condition_on_previous_text}"
        )

    def _init_model(self):
        """Initialize faster-whisper model."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError("faster-whisper required: pip install faster-whisper")

        logger.info(f"Loading Whisper model: {self.model_size} ({self.compute_type})")

        self.model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type
        )

        logger.info("Model loaded successfully")

    def transcribe_merged_segment(
        self,
        merged_segment: MergedSegment,
        speaker: str = "unknown",
        speaker_confidence: float = 0.0
    ) -> Optional[TranscriptSegmentWithConfidence]:
        """
        Transcribe a merged segment with confidence tracking.

        Args:
            merged_segment: Merged audio segment
            speaker: Speaker label (from upstream speaker ID)
            speaker_confidence: Speaker confidence

        Returns:
            TranscriptSegmentWithConfidence or None
        """
        start_time = time.time()

        # Ensure correct format
        audio = merged_segment.audio
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        try:
            # Transcribe with anti-hallucination settings
            segments_gen, info = self.model.transcribe(
                audio,
                language=self.asr_config.language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                condition_on_previous_text=self.condition_on_previous_text,
                temperature=0.0,  # Deterministic
                initial_prompt=self.initial_prompt
            )

            # Collect segments
            segments_list = list(segments_gen)

            if not segments_list:
                log_stage("ASR", "Empty transcript returned")
                return None

            # Aggregate transcript and confidence
            transcript_parts = []
            word_list = []

            # Track confidence across all sub-segments
            no_speech_probs = []
            avg_logprobs = []

            for seg in segments_list:
                if seg is None:
                    continue

                transcript_parts.append(seg.text)

                # Get confidence metrics
                if hasattr(seg, "no_speech_prob"):
                    no_speech_probs.append(seg.no_speech_prob)

                if hasattr(seg, "avg_logprob"):
                    avg_logprobs.append(seg.avg_logprob)

                # Collect words
                if hasattr(seg, "words") and seg.words:
                    for word in seg.words:
                        if word:
                            word_list.append({
                                "word": getattr(word, "word", ""),
                                "start": getattr(word, "start", 0.0),
                                "end": getattr(word, "end", 0.0),
                                "probability": getattr(word, "probability", 1.0)
                            })

            # Combine transcript
            text = " ".join(transcript_parts).strip()

            if not text:
                return None

            # Calculate average confidence
            avg_no_speech_prob = np.mean(no_speech_probs) if no_speech_probs else 0.0
            avg_logprob = np.mean(avg_logprobs) if avg_logprobs else -1.0

            # Create confidence metrics
            confidence = ConfidenceMetrics(
                no_speech_prob=avg_no_speech_prob,
                avg_logprob=avg_logprob
            )

            # Determine if low confidence
            is_low_confidence = (
                avg_no_speech_prob > self.no_speech_prob_threshold or
                avg_logprob < self.avg_logprob_threshold
            )

            # Handle language detection
            detected_lang = info.language
            lang_prob = info.language_probability

            # Language correction (Hindi/English code-switching)
            detected_lang = self._correct_language(text, detected_lang)

            # Create transcript segment
            result = TranscriptSegmentWithConfidence(
                text=text,
                start_time=merged_segment.start_time,
                end_time=merged_segment.end_time,
                duration_seconds=merged_segment.duration_seconds,
                language=detected_lang,
                language_probability=lang_prob,
                speaker=speaker,
                speaker_confidence=speaker_confidence,
                words=word_list,
                confidence_metrics=confidence,
                low_confidence=is_low_confidence,
                merge_count=merged_segment.merge_count,
                source_segments=len(merged_segment.source_segments)
            )

            # Update stats
            self.stats["segments_transcribed"] += 1
            self.stats["total_words"] += result.word_count

            if is_low_confidence:
                self.stats["low_confidence_flagged"] += 1

            # Log
            processing_time = time.time() - start_time
            rtf = processing_time / merged_segment.duration_seconds if merged_segment.duration_seconds > 0 else 0

            log_metric("ASR", "rtf", rtf)
            log_metric("ASR", "no_speech_prob", avg_no_speech_prob)
            log_metric("ASR", "avg_logprob", avg_logprob)

            marker = " ⚠️" if is_low_confidence else ""
            log_stage("ASR", f"[{result.word_count}w]{marker} {text[:60]}...")

            return result

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None

    def _correct_language(self, text: str, detected_lang: str) -> str:
        """
        Correct language detection for Hindi/English code-switching.
        Whisper sometimes misidentifies Hindi as Russian.
        """
        text_lower = text.lower()

        # Check for Devanagari
        hindi_chars = any("ऀ" <= c <= "ॿ" for c in text)

        # Check for Cyrillic
        cyrillic_chars = any("Ѐ" <= c <= "ӿ" for c in text)

        # Common Hindi words
        hindi_patterns = [
            "hai", "ka", "ki", "se", "mein", "aur", "kya",
            "nahi", "ho", "ke", "ko", "bhi", "ye", "thi"
        ]

        if detected_lang == "ru" and not cyrillic_chars:
            if hindi_chars or any(p in text_lower.split() for p in hindi_patterns):
                return "hi"
            else:
                return "en"

        return detected_lang

    def batch_transcribe(
        self,
        segments: List[MergedSegment],
        speaker_matches: List[tuple] = None
    ) -> List[TranscriptSegmentWithConfidence]:
        """
        Transcribe multiple merged segments.

        Args:
            segments: List of merged segments
            speaker_matches: Optional list of (speaker, confidence) tuples

        Returns:
            List of transcript segments with confidence
        """
        results = []

        for i, segment in enumerate(segments):
            # Get speaker info
            if speaker_matches and i < len(speaker_matches):
                speaker, speaker_conf = speaker_matches[i]
            else:
                speaker = "unknown"
                speaker_conf = 0.0

            result = self.transcribe_merged_segment(
                segment,
                speaker=speaker,
                speaker_confidence=speaker_conf
            )

            if result:
                results.append(result)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get transcription statistics."""
        return self.stats.copy()


def test_batch_asr(audio_path: str, config_path: str = None):
    """Test batch ASR on an audio file."""
    import librosa
    from config.settings import Config
    from vad.silero_vad import VADProcessor
    from vad.segment_merger import SegmentMerger

    print(f"\nTesting batch ASR on: {audio_path}")

    # Load config
    if config_path:
        config = Config.from_yaml(config_path)
    else:
        config = Config()

    # Initialize components
    vad = VADProcessor(config)
    merger = SegmentMerger(config)
    asr = BatchASRProcessor(config)

    # Load audio
    audio, sr = librosa.load(audio_path, sr=16000, mono=True)

    print(f"\nAudio duration: {len(audio)/sr:.2f}s")

    # VAD
    vad_segments = vad.process_audio_chunk(audio, datetime.now())
    print(f"VAD segments: {len(vad_segments)}")

    # Merge
    merged = merger.add_segments_batch(vad_segments)
    print(f"Merged units: {len(merged)}")

    # Transcribe
    for i, unit in enumerate(merged, 1):
        print(f"\n--- Unit {i} ({unit.duration_seconds:.1f}s) ---")
        result = asr.transcribe_merged_segment(unit)

        if result:
            print(f"Language: {result.language}")
            print(f"Words: {result.word_count}")
            print(f"Confidence: no_speech={result.confidence_metrics.no_speech_prob:.2f}, "
                  f"logprob={result.confidence_metrics.avg_logprob:.2f}")
            print(f"Low confidence: {result.low_confidence}")
            print(f"\nTranscript:\n{result.text}")

    # Stats
    print(f"\n--- Stats ---")
    for k, v in asr.get_stats().items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        config_path = sys.argv[2] if len(sys.argv) > 2 else None
        test_batch_asr(sys.argv[1], config_path)
    else:
        print("Usage: python -m voice_journal.asr.transcriber_batch <audio_file> [config_path]")
