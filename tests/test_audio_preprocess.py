"""Tests for audio preprocessing module."""

import numpy as np
import pytest

from audio_capture.preprocess import AudioPreprocessor, PreprocessedAudio
from config.settings import Config


class TestAudioPreprocessor:
    """Tests for AudioPreprocessor class."""

    def test_init(self):
        """Test preprocessor initialization."""
        config = Config()
        preprocessor = AudioPreprocessor(config)

        assert preprocessor.enable_denoising == config.preprocessing.enable_denoising
        assert preprocessor.gain_normalization == config.preprocessing.gain_normalization

    def test_preprocess_basic(self):
        """Test basic preprocessing."""
        config = Config()
        config.preprocessing.enable_denoising = False  # Skip denoising for test
        preprocessor = AudioPreprocessor(config)

        # Create test audio
        sample_rate = 16000
        duration = 5.0
        audio = np.random.randn(int(duration * sample_rate)).astype(np.float32) * 0.1

        result = preprocessor.preprocess(audio, sample_rate)

        assert result.original_duration == duration
        assert result.sample_rate == sample_rate
        assert len(result.audio) == len(audio)

    def test_gain_normalization(self):
        """Test gain normalization."""
        config = Config()
        config.preprocessing.enable_denoising = False
        config.preprocessing.gain_normalization = True
        config.preprocessing.target_db = -20.0
        preprocessor = AudioPreprocessor(config)

        # Create very quiet audio
        sample_rate = 16000
        audio = np.random.randn(16000).astype(np.float32) * 0.001

        result = preprocessor.preprocess(audio, sample_rate)

        assert result.normalized == True
        # Processed audio should be louder
        assert result.processed_rms_db > result.original_rms_db

    def test_mono_conversion(self):
        """Test stereo to mono conversion."""
        config = Config()
        config.preprocessing.enable_denoising = False
        preprocessor = AudioPreprocessor(config)

        # Create stereo audio
        sample_rate = 16000
        audio_stereo = np.random.randn(16000, 2).astype(np.float32)

        result = preprocessor.preprocess(audio_stereo, sample_rate)

        assert result.audio.ndim == 1

    def test_calculate_rms_db(self):
        """Test RMS dB calculation."""
        config = Config()
        preprocessor = AudioPreprocessor(config)

        # Known signal: 1.0 amplitude
        audio = np.array([1.0, -1.0, 1.0, -1.0], dtype=np.float32)
        rms_db = preprocessor._calculate_rms_db(audio)

        # RMS of [1, -1, 1, -1] is 1.0, which is 0 dB
        assert rms_db == pytest.approx(0.0, abs=0.1)

    def test_empty_audio_rms(self):
        """Test RMS calculation for empty audio."""
        config = Config()
        preprocessor = AudioPreprocessor(config)

        audio = np.array([], dtype=np.float32)
        rms_db = preprocessor._calculate_rms_db(audio)

        assert rms_db < -90  # Should be very quiet
