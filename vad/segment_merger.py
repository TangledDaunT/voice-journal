"""
Segment Merging Module.
Merges consecutive VAD segments before they reach ASR.
This is critical for preventing hallucination on short, isolated segments.
"""

import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from config.settings import Config, SegmentMergingConfig
from vad.silero_vad import SpeechSegment
from utils.logger import logger, log_stage, log_metric


@dataclass
class MergedSegment:
    """
    A merged transcription unit composed of multiple VAD segments.
    This is what gets sent to ASR (not individual VAD segments).
    """
    # Time bounds
    start_time: datetime
    end_time: datetime

    # Audio data
    audio: np.ndarray
    sample_rate: int

    # Source VAD segments that were merged
    source_segments: List[SpeechSegment] = field(default_factory=list)

    # Metadata
    merge_count: int = 1  # How many VAD segments were merged
    gaps_merged: int = 0  # How many gaps were bridged
    total_gap_duration_seconds: float = 0.0

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    @property
    def avg_source_duration(self) -> float:
        if not self.source_segments:
            return 0.0
        return sum(s.duration_seconds for s in self.source_segments) / len(self.source_segments)

    @property
    def speech_ratio(self) -> float:
        """Ratio of actual speech time to total duration."""
        if not self.source_segments:
            return 0.0
        total_speech = sum(s.duration_seconds for s in self.source_segments)
        return total_speech / self.duration_seconds if self.duration_seconds > 0 else 0.0


class SegmentMerger:
    """
    Merges consecutive VAD segments into larger transcription units.
    This prevents Whisper from hallucinating on short, isolated segments.

    Key parameters:
    - merge_gap_seconds: Merge segments separated by less than this gap
    - min_transcription_unit_seconds: Don't send segments shorter than this to ASR
    - max_transcription_unit_seconds: Split merged units if they exceed this
    """

    def __init__(self, config: Config):
        self.config = config
        merging_config = config.segment_merging

        self.merge_gap_seconds = merging_config.merge_gap_seconds
        self.min_unit_seconds = merging_config.min_transcription_unit_seconds
        self.max_unit_seconds = merging_config.max_transcription_unit_seconds

        # In-memory queue for managing segment merging
        self.pending_segments: List[SpeechSegment] = []
        self.pending_audio_chunks: List[np.ndarray] = []

        logger.info(
            f"SegmentMerger initialized: "
            f"merge_gap={self.merge_gap_seconds}s, "
            f"min_unit={self.min_unit_seconds}s, "
            f"max_unit={self.max_unit_seconds}s"
        )

    def add_segment(
        self,
        segment: SpeechSegment
    ) -> Optional[MergedSegment]:
        """
        Add a VAD segment and check if we have a complete transcription unit.

        Returns:
            MergedSegment if ready to transcribe, None otherwise
        """
        self.pending_segments.append(segment)

        # Check if we should flush based on gap to next segment
        # (In batch mode, we call finalize() explicitly at end)
        return None

    def add_segments_batch(
        self,
        segments: List[SpeechSegment]
    ) -> List[MergedSegment]:
        """
        Process a batch of VAD segments and return merged transcription units.

        This is the main entry point for batch processing.
        """
        if not segments:
            return []

        # Sort by start time
        sorted_segments = sorted(segments, key=lambda s: s.start_time)

        merged_units = []
        current_group: List[SpeechSegment] = []
        current_audio_chunks: List[np.ndarray] = []

        for segment in sorted_segments:
            if not current_group:
                # Start new group
                current_group.append(segment)
                current_audio_chunks.append(segment.audio)
                continue

            # Check gap to previous segment
            prev_segment = current_group[-1]
            gap_seconds = (segment.start_time - prev_segment.end_time).total_seconds()

            if gap_seconds <= self.merge_gap_seconds:
                # Merge: add to current group
                current_group.append(segment)
                current_audio_chunks.append(segment.audio)

            else:
                # Gap too large: finalize current group and start new one
                merged_unit = self._create_merged_unit(current_group, current_audio_chunks)

                # Only add if meets minimum duration, else hold
                if merged_unit.duration_seconds >= self.min_unit_seconds:
                    # Split if exceeds max duration
                    if merged_unit.duration_seconds > self.max_unit_seconds:
                        split_units = self._split_merged_unit(merged_unit)
                        merged_units.extend(split_units)
                    else:
                        merged_units.append(merged_unit)
                else:
                    # Too short - we'll need to handle this case
                    # For now, log a warning and add anyway (better than losing data)
                    log_stage("Merge", f"Warning: short unit {merged_unit.duration_seconds:.1f}s (min={self.min_unit_seconds}s)")
                    merged_units.append(merged_unit)

                # Start new group
                current_group = [segment]
                current_audio_chunks = [segment.audio]

        # Don't forget remaining segments
        if current_group:
            merged_unit = self._create_merged_unit(current_group, current_audio_chunks)

            if merged_unit.duration_seconds >= self.min_unit_seconds:
                if merged_unit.duration_seconds > self.max_unit_seconds:
                    split_units = self._split_merged_unit(merged_unit)
                    merged_units.extend(split_units)
                else:
                    merged_units.append(merged_unit)
            else:
                log_stage("Merge", f"Warning: short final unit {merged_unit.duration_seconds:.1f}s")
                merged_units.append(merged_unit)

        log_stage("Merge", f"{len(segments)} VAD segments → {len(merged_units)} transcription units")

        return merged_units

    def _create_merged_unit(
        self,
        segments: List[SpeechSegment],
        audio_chunks: List[np.ndarray]
    ) -> MergedSegment:
        """Create a merged transcription unit from segments."""
        if not segments:
            raise ValueError("Cannot create merged unit from empty segments")

        # Combine audio with small gaps filled with silence
        # This preserves timing for downstream processing
        merged_audio = self._merge_audio_with_timing(segments, audio_chunks)

        # Calculate statistics
        gaps = []
        for i in range(len(segments) - 1):
            gap = (segments[i+1].start_time - segments[i].end_time).total_seconds()
            if gap > 0:
                gaps.append(gap)

        total_gap = sum(gaps)

        merged_unit = MergedSegment(
            start_time=segments[0].start_time,
            end_time=segments[-1].end_time,
            audio=merged_audio,
            sample_rate=segments[0].sample_rate,
            source_segments=segments,
            merge_count=len(segments),
            gaps_merged=len(gaps),
            total_gap_duration_seconds=total_gap
        )

        log_metric("Merge", "merge_count", merged_unit.merge_count)
        log_metric("Merge", "total_gap_merged", total_gap, "s")

        return merged_unit

    def _merge_audio_with_timing(
        self,
        segments: List[SpeechSegment],
        audio_chunks: List[np.ndarray]
    ) -> np.ndarray:
        """
        Merge audio chunks, filling gaps with silence.
        This preserves timing alignment.
        """
        if not segments:
            return np.array([], dtype=np.float32)

        sample_rate = segments[0].sample_rate

        # Calculate total duration including gaps
        start_time = segments[0].start_time
        end_time = segments[-1].end_time
        total_duration = (end_time - start_time).total_seconds()
        total_samples = int(total_duration * sample_rate)

        # Create output buffer
        merged = np.zeros(total_samples, dtype=np.float32)

        # Place each segment in the correct position
        for segment, audio in zip(segments, audio_chunks):
            # Calculate offset from start
            offset_seconds = (segment.start_time - start_time).total_seconds()
            offset_samples = int(offset_seconds * sample_rate)

            # Copy segment audio (handle edge cases where sizes don't align perfectly)
            segment_samples = len(audio)
            end_samples = min(offset_samples + segment_samples, total_samples)
            actual_samples = end_samples - offset_samples
            if actual_samples > 0 and offset_samples >= 0:
                merged[offset_samples:end_samples] = audio[:actual_samples]

        return merged

    def _split_merged_unit(
        self,
        merged_unit: MergedSegment
    ) -> List[MergedSegment]:
        """
        Split a merged unit if it exceeds max duration.
        Tries to split at natural gaps between source segments.
        """
        if merged_unit.duration_seconds <= self.max_unit_seconds:
            return [merged_unit]

        # Try to split at large gaps in source segments
        segments = merged_unit.source_segments

        if len(segments) == 1:
            # Single long segment - split evenly
            return self._split_single_segment(merged_unit)

        # Find best split point (largest gap)
        gaps = []
        for i in range(len(segments) - 1):
            gap_start = segments[i].end_time
            gap_end = segments[i+1].start_time
            gap_duration = (gap_end - gap_start).total_seconds()
            gaps.append((i, gap_start, gap_end, gap_duration))

        # Find gap that would result in roughly equal halves
        total_duration = merged_unit.duration_seconds
        target_split_time = merged_unit.start_time + timedelta(seconds=total_duration / 2)

        # Find gap closest to middle
        best_gap = min(gaps, key=lambda g: abs((g[1] - target_split_time).total_seconds()))

        split_idx = best_gap[0]

        # Create two merged units
        first_segments = segments[:split_idx+1]
        first_audio = [s.audio for s in first_segments]

        second_segments = segments[split_idx+1:]
        second_audio = [s.audio for s in second_segments]

        unit1 = self._create_merged_unit(first_segments, first_audio)
        unit2 = self._create_merged_unit(second_segments, second_audio)

        # Recursively split if still too long
        result = []
        for unit in [unit1, unit2]:
            if unit.duration_seconds > self.max_unit_seconds:
                result.extend(self._split_merged_unit(unit))
            else:
                result.append(unit)

        return result

    def _split_single_segment(
        self,
        merged_unit: MergedSegment
    ) -> List[MergedSegment]:
        """Split a single long segment into even chunks."""
        audio = merged_unit.audio
        sample_rate = merged_unit.sample_rate

        max_samples = int(self.max_unit_seconds * sample_rate)
        total_samples = len(audio)

        split_units = []
        current_start_sample = 0
        current_start_time = merged_unit.start_time

        while current_start_sample < total_samples:
            current_end_sample = min(current_start_sample + max_samples, total_samples)
            chunk_samples = current_end_sample - current_start_sample
            chunk_duration = chunk_samples / sample_rate

            chunk_audio = audio[current_start_sample:current_end_sample]

            chunk_end_time = current_start_time + timedelta(seconds=chunk_duration)

            # Create synthetic source segment
            from vad.silero_vad import SpeechSegment
            synthetic_source = SpeechSegment(
                start_time=current_start_time,
                end_time=chunk_end_time,
                audio=chunk_audio,
                sample_rate=sample_rate
            )

            split_unit = MergedSegment(
                start_time=current_start_time,
                end_time=chunk_end_time,
                audio=chunk_audio,
                sample_rate=sample_rate,
                source_segments=[synthetic_source],
                merge_count=1,
                gaps_merged=0,
                total_gap_duration_seconds=0.0
            )

            split_units.append(split_unit)

            # Advance to next chunk
            current_start_sample = current_end_sample
            current_start_time = chunk_end_time

        return split_units

    def finalize(self) -> Optional[MergedSegment]:
        """
        Finalize any pending segments.
        Call this when flushing the pipeline.
        """
        if not self.pending_segments:
            return None

        merged_unit = self._create_merged_unit(
            self.pending_segments,
            self.pending_audio_chunks
        )

        self.pending_segments = []
        self.pending_audio_chunks = []

        return merged_unit


def test_segment_merging(audio_path: str):
    """Test segment merging on an audio file."""
    import librosa
    from config.settings import Config
    from vad.silero_vad import VADProcessor

    print(f"\nTesting segment merging on: {audio_path}")

    config = Config()
    vad = VADProcessor(config)
    merger = SegmentMerger(config)

    # Load and process
    audio, sr = librosa.load(audio_path, sr=16000, mono=True)
    segments = vad.process_audio_chunk(audio, datetime.now())

    print(f"\n{len(segments)} VAD segments detected:")
    for i, seg in enumerate(segments, 1):
        print(f"  {i}. {seg.duration_seconds:.2f}s")

    # Merge
    merged_units = merger.add_segments_batch(segments)

    print(f"\n{len(merged_units)} transcription units:")
    for i, unit in enumerate(merged_units, 1):
        print(f"  {i}. {unit.duration_seconds:.2f}s (merged from {unit.merge_count} segments)")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_segment_merging(sys.argv[1])
    else:
        print("Usage: python -m voice_journal.vad.segment_merger <audio_file>")
