"""
Stage 2: Voice Activity Detection using Silero VAD.
Emits discrete speech segments from continuous audio stream.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import numpy as np

from config.settings import Config
from utils.logger import logger, log_stage, log_metric


@dataclass
class SpeechSegment:
    """A detected speech segment with timing and optional audio."""
    start_time: datetime
    end_time: datetime
    audio: np.ndarray  # The audio data
    sample_rate: int
    start_offset_seconds: float = 0.0  # Offset from start of buffer

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    @property
    def duration_ms(self) -> int:
        return int(self.duration_seconds * 1000)

    @property
    def samples(self) -> int:
        return self.audio.shape[0]


class SileroVAD:
    """
    Silero VAD model wrapper using torch hub.
    CPU-friendly voice activity detection.
    """

    HOP_SIZE = 512
    SAMPLE_RATE = 16000

    def __init__(self, model_path: str, threshold: float = 0.5):
        self.model_path = model_path
        self.threshold = threshold
        self.model = None
        self.utils = None
        self._init_model()

    def _init_model(self):
        """Initialize Silero VAD model from torch hub with error handling."""
        import torch

        try:
            logger.info("Loading Silero VAD model from torch hub...")

            # Set hub directory for caching
            torch_hub_dir = Path.home() / ".cache" / "torch" / "hub"
            torch_hub_dir.mkdir(parents=True, exist_ok=True)

            self.model, self.utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True
            )
            self.model.eval()
            logger.info("Silero VAD loaded successfully from torch hub")

        except Exception as e:
            logger.error(f"Failed to load Silero VAD from torch hub: {e}")

            # Try loading from local cache
            try:
                logger.info("Attempting to load from local cache...")
                cache_dir = torch_hub_dir / 'snakers4_silero-vad_master'

                if cache_dir.exists():
                    self.model, self.utils = torch.hub.load(
                        repo_or_dir=str(cache_dir),
                        model='silero_vad',
                        source='local',
                        force_reload=False
                    )
                    self.model.eval()
                    logger.info("Silero VAD loaded from local cache")
                else:
                    raise RuntimeError("No cached model found")

            except Exception as cache_error:
                logger.error(f"Failed to load from cache: {cache_error}")
                logger.error("Please ensure internet connection and run again, or manually download model to ~/.cache/torch/hub/snakers4_silero-vad_master")
                raise RuntimeError("Failed to initialize VAD model. Check internet connection or manually download the model.")

    def detect_speech(self, audio: np.ndarray) -> List[tuple]:
        """Detect speech segments in audio buffer."""
        import torch

        if audio.ndim == 2:
            audio = audio[:, 0]

        audio_tensor = torch.from_numpy(audio.astype(np.float32))

        # Get speech timestamps using the utility function
        speech_timestamps = self.utils[0](
            audio_tensor,
            self.model,
            threshold=self.threshold,
            sampling_rate=self.SAMPLE_RATE,
            min_speech_duration_ms=300,
            min_silence_duration_ms=100
        )

        segments = []
        for ts in speech_timestamps:
            segments.append((
                ts['start'],
                ts['end'],
                0.8  # Default confidence
            ))

        return segments


class VADProcessor:
    """
    Stage 2 processor: VAD segment detection.
    Processes continuous audio stream and emits speech segments.
    """

    def __init__(self, config: Config):
        self.config = config
        self.vad = SileroVAD(
            model_path=config.vad.model_path,
            threshold=config.vad.threshold
        )
        self.min_segment_duration = config.vad.min_segment_duration
        self.silence_padding = config.vad.silence_padding
        self.max_segment_duration = config.vad.max_segment_duration
        logger.info(f"VADProcessor initialized: threshold={config.vad.threshold}")

    def process_audio_chunk(
        self,
        audio: np.ndarray,
        reference_time: datetime
    ) -> List[SpeechSegment]:
        """Process an audio chunk and extract speech segments."""
        import time
        start_time = time.time()

        segments = self.vad.detect_speech(audio)
        log_metric("VAD", "detection_time", time.time() - start_time, "s")

        speech_segments = []
        for start_sample, end_sample, mean_prob in segments:
            padding_samples = int(self.silence_padding * SileroVAD.SAMPLE_RATE)
            start_sample = max(0, start_sample - padding_samples)
            end_sample = min(len(audio), end_sample + padding_samples)

            duration = (end_sample - start_sample) / SileroVAD.SAMPLE_RATE

            if duration < self.min_segment_duration:
                continue

            if duration > self.max_segment_duration:
                speech_segments.extend(
                    self._split_long_segment(audio, start_sample, end_sample, reference_time)
                )
            else:
                segment_audio = audio[start_sample:end_sample]
                start_offset = start_sample / SileroVAD.SAMPLE_RATE

                segment = SpeechSegment(
                    start_time=datetime.fromtimestamp(reference_time.timestamp() + start_offset),
                    end_time=datetime.fromtimestamp(reference_time.timestamp() + start_offset + duration),
                    audio=segment_audio,
                    sample_rate=SileroVAD.SAMPLE_RATE,
                    start_offset_seconds=start_offset
                )
                speech_segments.append(segment)
                log_stage("VAD", f"Segment: {duration:.2f}s")

        return speech_segments

    def _split_long_segment(
        self,
        audio: np.ndarray,
        start_sample: int,
        end_sample: int,
        reference_time: datetime
    ) -> List[SpeechSegment]:
        """Split a long speech segment into smaller chunks."""
        max_samples = int(self.max_segment_duration * SileroVAD.SAMPLE_RATE)
        segments = []

        current_start = start_sample
        while current_start < end_sample:
            current_end = min(current_start + max_samples, end_sample)
            segment_audio = audio[current_start:current_end]
            duration = len(segment_audio) / SileroVAD.SAMPLE_RATE
            start_offset = current_start / SileroVAD.SAMPLE_RATE

            segment = SpeechSegment(
                start_time=datetime.fromtimestamp(reference_time.timestamp() + start_offset),
                end_time=datetime.fromtimestamp(reference_time.timestamp() + start_offset + duration),
                audio=segment_audio,
                sample_rate=SileroVAD.SAMPLE_RATE,
                start_offset_seconds=start_offset
            )
            segments.append(segment)
            current_start = current_end

        return segments


def test_vad(audio_path: str):
    """Test VAD on a pre-recorded audio file."""
    import librosa

    print(f"Loading audio: {audio_path}")
    audio, sr = librosa.load(audio_path, sr=16000, mono=True)

    print(f"Audio: {len(audio)/sr:.2f}s")

    vad_processor = VADProcessor(Config())
    segments = vad_processor.process_audio_chunk(audio, datetime.now())

    print(f"\nDetected {len(segments)} speech segments:")
    for i, seg in enumerate(segments, 1):
        print(f"  {i}. {seg.duration_seconds:.2f}s")

    return segments


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_vad(sys.argv[1])
