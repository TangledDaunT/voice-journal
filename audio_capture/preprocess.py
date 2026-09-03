"""
Audio Preprocessing Module.
Applies denoising and gain normalization before VAD/ASR.
"""

import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass

from config.settings import Config, PreprocessingConfig
from utils.logger import logger, log_stage, log_metric


@dataclass
class PreprocessedAudio:
    """Result of audio preprocessing."""
    audio: np.ndarray
    sample_rate: int
    original_duration: float
    denoised: bool
    normalized: bool
    original_rms_db: float
    processed_rms_db: float


class AudioPreprocessor:
    """
    Preprocesses audio before VAD and ASR.
    Applies denoising and gain normalization to improve transcription quality.
    """

    def __init__(self, config: Config):
        self.config = config
        self.preprocessing_config = config.preprocessing

        self.enable_denoising = self.preprocessing_config.enable_denoising
        self.denoising_method = self.preprocessing_config.denoising_method
        self.gain_normalization = self.preprocessing_config.gain_normalization
        self.target_db = self.preprocessing_config.target_db

        # Lazy-load denoising library
        self._noisereduce = None
        self._rnnoise = None

        logger.info(
            f"AudioPreprocessor initialized: "
            f"denoise={self.enable_denoising} ({self.denoising_method}), "
            f"normalize={self.gain_normalization} (target={self.target_db}dB)"
        )

    def _load_noisereduce(self):
        """Lazy-load noisereduce library."""
        if self._noisereduce is None:
            try:
                import noisereduce
                self._noisereduce = noisereduce
            except ImportError:
                logger.warning(
                    "noisereduce not installed. "
                    "Install with: pip install noisereduce"
                )
                self._noisereduce = None
        return self._noisereduce

    def preprocess(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000
    ) -> PreprocessedAudio:
        """
        Preprocess audio: denoise and normalize gain.

        Args:
            audio: Audio data as numpy array
            sample_rate: Sample rate (default 16000)

        Returns:
            PreprocessedAudio with processed audio and metadata
        """
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Ensure mono
        if audio.ndim == 2:
            audio = audio[:, 0]

        original_duration = len(audio) / sample_rate
        original_rms_db = self._calculate_rms_db(audio)

        denoised = False
        normalized = False
        processed_audio = audio.copy()

        # Apply denoising
        if self.enable_denoising:
            processed_audio = self._apply_denoising(processed_audio, sample_rate)
            denoised = True

        # Apply gain normalization
        if self.gain_normalization:
            processed_audio = self._normalize_gain(processed_audio, self.target_db)
            normalized = True

        processed_rms_db = self._calculate_rms_db(processed_audio)

        log_metric("Preprocessing", "original_rms_db", original_rms_db, "dB")
        log_metric("Preprocessing", "processed_rms_db", processed_rms_db, "dB")

        return PreprocessedAudio(
            audio=processed_audio,
            sample_rate=sample_rate,
            original_duration=original_duration,
            denoised=denoised,
            normalized=normalized,
            original_rms_db=original_rms_db,
            processed_rms_db=processed_rms_db
        )

    def _apply_denoising(
        self,
        audio: np.ndarray,
        sample_rate: int
    ) -> np.ndarray:
        """Apply denoising based on configured method."""
        start_time = None
        import time

        if self.denoising_method == "noisereduce":
            nr = self._load_noisereduce()
            if nr is None:
                log_stage("Preprocessing", "noisereduce not available, skipping denoise")
                return audio

            start_time = time.time()
            try:
                # noisereduce works on float32 audio
                denoised = nr.reduce_noise(
                    y=audio,
                    sr=sample_rate,
                    stationary=True,  # For consistent background noise
                    prop_decrease=0.75  # Moderate noise reduction
                )
                log_metric("Preprocessing", "denoise_time", time.time() - start_time, "s")
                return denoised.astype(np.float32)

            except Exception as e:
                logger.error(f"Denoising failed: {e}")
                return audio

        elif self.denoising_method == "rnnoise":
            try:
                from pyrnnoise import RNNoise
            except ImportError:
                logger.warning("RNNoise unavailable; install pyrnnoise to use this backend")
                return audio

            try:
                denoiser = RNNoise(sample_rate)
                int16_audio = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
                frames = [
                    denoised_frame
                    for _, denoised_frame in denoiser.denoise_chunk(
                        int16_audio[np.newaxis, :], partial=True
                    )
                ]
                if not frames:
                    return audio
                denoised = np.concatenate(frames, axis=1).reshape(-1)
                return (denoised.astype(np.float32) / 32767.0)[:len(audio)]
            except Exception as e:
                logger.error(f"RNNoise failed: {e}")
                return audio

        else:
            logger.warning(f"Unknown denoising method: {self.denoising_method}")
            return audio

    def _normalize_gain(
        self,
        audio: np.ndarray,
        target_db: float
    ) -> np.ndarray:
        """
        Normalize audio to target dB level.

        Args:
            audio: Audio data
            target_db: Target loudness in dB (e.g., -20)

        Returns:
            Normalized audio
        """
        # Calculate current RMS
        current_rms_db = self._calculate_rms_db(audio)

        # If audio is too quiet or too loud, adjust
        if current_rms_db < -60:
            # Very quiet audio, likely silence
            return audio

        # Calculate gain needed
        gain_db = target_db - current_rms_db
        gain_linear = 10 ** (gain_db / 20)

        # Apply gain
        normalized = audio * gain_linear

        # Clip to prevent clipping
        max_val = np.max(np.abs(normalized))
        if max_val > 0.99:
            normalized = normalized / max_val * 0.99

        return normalized.astype(np.float32)

    def _calculate_rms_db(self, audio: np.ndarray) -> float:
        """Calculate RMS level in dB."""
        if len(audio) == 0:
            return -100.0

        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 1e-10:
            return -100.0

        return 20 * np.log10(rms)

    def preprocess_batch(
        self,
        segments: list
    ) -> list:
        """
        Preprocess multiple audio segments.

        Args:
            segments: List of SpeechSegment objects

        Returns:
            List of PreprocessedAudio objects
        """
        results = []
        for segment in segments:
            preprocessed = self.preprocess(segment.audio, segment.sample_rate)
            # Update segment audio in place
            segment.audio = preprocessed.audio
            results.append(preprocessed)

        return results


def test_preprocessing(audio_path: str):
    """Test audio preprocessing on a file."""
    import librosa
    from config.settings import Config

    print(f"\nTesting preprocessing on: {audio_path}")

    config = Config()
    preprocessor = AudioPreprocessor(config)

    # Load audio
    audio, sr = librosa.load(audio_path, sr=16000, mono=True)
    print(f"  Duration: {len(audio)/sr:.2f}s")

    # Preprocess
    result = preprocessor.preprocess(audio, sr)

    print(f"\n  Original RMS: {result.original_rms_db:.1f} dB")
    print(f"  Processed RMS: {result.processed_rms_db:.1f} dB")
    print(f"  Denoised: {result.denoised}")
    print(f"  Normalized: {result.normalized}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_preprocessing(sys.argv[1])
    else:
        print("Usage: python -m voice_journal.audio_capture.preprocess <audio_file>")
