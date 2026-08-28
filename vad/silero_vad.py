"""
Stage 2: Voice Activity Detection using Silero VAD.
Emits discrete speech segments from continuous audio stream.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Generator, Callable
import numpy as np
import onnxruntime as ort

from ..config.settings import Config
from ..utils.logger import logger, log_stage, log_metric


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
    Silero VAD model wrapper.
    CPU-friendly voice activity detection.
    """

    # Silero VAD constants
    HOP_SIZE = 512  # Samples per frame
    SAMPLE_RATE = 16000  # Fixed sample rate for Silero

    def __init__(self, model_path: str, threshold: float = 0.5):
        self.model_path = model_path
        self.threshold = threshold

        # Initialize model
        self._init_model()

    def _init_model(self):
        """Initialize ONNX model for Silero VAD."""
        # Download model if not present
        if not os.path.exists(self.model_path):
            self._download_model()

        # Load ONNX model
        opts = ort.SessionOptions()
        opts.intra_num_threads = 1
        opts.inter_op_num_threads = 1
        opts.log_verbosity_level = 3

        self.session = ort.InferenceSession(
            self.model_path,
            sess_options=opts,
            providers=['CPUExecutionProvider']
        )

        # Get model inputs/outputs
        self.inputs = {inp.name: inp for inp in self.session.get_inputs()}
        self.outputs = {out.name: out for out in self.session.get_outputs()}

        # Initialize hidden states
        self._reset_states()

        logger.info(f"Silero VAD loaded: {self.model_path}")

    def _download_model(self):
        """Download Silero VAD model from official source."""
        import urllib.request

        model_dir = os.path.dirname(self.model_path)
        os.makedirs(model_dir, exist_ok=True)

        url = "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx"
        logger.info(f"Downloading Silero VAD model from {url}")

        urllib.request.urlretrieve(url, self.model_path)
        logger.info(f"Model downloaded to {self.model_path}")

    def _reset_states(self):
        """Reset hidden states for new audio stream."""
        self.h = np.zeros((2, 1, 64), dtype=np.float32)
        self.c = np.zeros((2, 1, 64), dtype=np.float32)

    def _process_chunk(self, audio_chunk: np.ndarray) -> float:
        """
        Process a single audio chunk through VAD.
        Returns probability of speech.

        Args:
            audio_chunk: Float32 array of shape (HOP_SIZE,) or (HOP_SIZE, 1)

        Returns:
            float: Speech probability [0, 1]
        """
        # Ensure correct shape
        if audio_chunk.ndim == 1:
            audio_chunk = audio_chunk.reshape(1, -1)
        elif audio_chunk.shape[0] == audio_chunk.size:
            audio_chunk = audio_chunk.reshape(1, -1)

        # Run inference
        inputs = {
            'input': audio_chunk,
            'h': self.h,
            'c': self.c
        }

        outputs = self.session.run(None, inputs)

        # Extract speech probability and updated states
        speech_prob = outputs[0][0, 0]  # Shape: (1, 1)
        self.h = outputs[1]
        self.c = outputs[2]

        return float(speech_prob)

    def detect_speech(
        self,
        audio: np.ndarray,
        return_timestamps: bool = True
    ) -> List[tuple]:
        """
        Detect speech segments in audio buffer.

        Args:
            audio: Float32 array of audio samples (1D or 2D)
            return_timestamps: Return frame-level timestamps

        Returns:
            List of (start_frame, end_frame, speech_prob_mean) tuples
        """
        # Ensure mono
        if audio.ndim == 2:
            audio = audio[:, 0]

        # Reset states for new segment
        self._reset_states()

        # Calculate number of chunks
        n_chunks = len(audio) // self.HOP_SIZE
        if n_chunks == 0:
            return []

        # Process each chunk
        speech_probs = []
        for i in range(n_chunks):
            chunk = audio[i * self.HOP_SIZE:(i + 1) * self.HOP_SIZE].astype(np.float32)
            prob = self._process_chunk(chunk)
            speech_probs.append(prob)

        # Find speech segments
        segments = []
        in_speech = False
        start_frame = 0

        for i, prob in enumerate(speech_probs):
            if prob >= self.threshold and not in_speech:
                # Speech starts
                in_speech = True
                start_frame = i
            elif prob < self.threshold and in_speech:
                # Speech ends
                in_speech = False
                end_frame = i
                segments.append((
                    start_frame * self.HOP_SIZE,
                    end_frame * self.HOP_SIZE,
                    np.mean(speech_probs[start_frame:end_frame])
                ))

        # Handle speech continuing to end
        if in_speech:
            segments.append((
                start_frame * self.HOP_SIZE,
                len(speech_probs) * self.HOP_SIZE,
                np.mean(speech_probs[start_frame:])
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
        """
        Process an audio chunk and extract speech segments.

        Args:
            audio: Audio buffer as float32 array
            reference_time: Timestamp for the start of this audio

        Returns:
            List of SpeechSegment objects
        """
        import time
        start_time = time.time()

        # Detect speech
        segments = self.vad.detect_speech(audio)
        log_metric("VAD", "detection_time", time.time() - start_time, "s")

        # Convert to SpeechSegment objects
        speech_segments = []

        for start_sample, end_sample, mean_prob in segments:
            # Apply silence padding
            padding_samples = int(self.silence_padding * SileroVAD.SAMPLE_RATE)
            start_sample = max(0, start_sample - padding_samples)
            end_sample = min(len(audio), end_sample + padding_samples)

            # Calculate timing
            duration = (end_sample - start_sample) / SileroVAD.SAMPLE_RATE

            # Filter by minimum duration
            if duration < self.min_segment_duration:
                log_stage("VAD", f"Rejecting segment < {self.min_segment_duration}s: {duration:.2f}s")
                continue

            # Split if too long
            if duration > self.max_segment_duration:
                log_stage("VAD", f"Splitting segment > {self.max_segment_duration}s")
                speech_segments.extend(
                    self._split_long_segment(audio, start_sample, end_sample, reference_time)
                )
            else:
                # Create segment
                segment_audio = audio[start_sample:end_sample]
                start_offset = start_sample / SileroVAD.SAMPLE_RATE

                segment = SpeechSegment(
                    start_time=reference_time,
                    end_time=datetime.fromtimestamp(
                        reference_time.timestamp() + duration
                    ),
                    audio=segment_audio,
                    sample_rate=SileroVAD.SAMPLE_RATE,
                    start_offset_seconds=start_offset
                )

                speech_segments.append(segment)

                log_stage("VAD", f"Segment: {duration:.2f}s, prob={mean_prob:.2f}")

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
                start_time=reference_time,
                end_time=datetime.fromtimestamp(
                    reference_time.timestamp() + duration
                ),
                audio=segment_audio,
                sample_rate=SileroVAD.SAMPLE_RATE,
                start_offset_seconds=start_offset
            )

            segments.append(segment)
            current_start = current_end

        return segments


# Convenience function for testing
def test_vad(audio_path: str, model_path: str = "./models/silero_vad.onnx"):
    """Test VAD on a pre-recorded audio file."""
    import librosa

    print(f"Loading audio: {audio_path}")
    audio, sr = librosa.load(audio_path, sr=16000, mono=True)

    print(f"Audio loaded: {len(audio)} samples, {len(audio)/sr:.2f}s")

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
    else:
        print("Usage: python -m voice_journal.vad <audio_file>")
