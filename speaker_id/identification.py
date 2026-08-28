"""
Stage 3: Speaker Identification.
Matches speech segments to calibrated voice profiles (Shreyansh/Shivangi).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple
import warnings

import numpy as np

from ..config.settings import Config, load_voice_profiles, SpeakerProfile
from ..vad.silero_vad import SpeechSegment
from ..utils.logger import logger, log_stage, log_metric

warnings.filterwarnings("ignore", message="PySoundFile failed.*")


@dataclass
class SpeakerMatch:
    """Result of speaker matching for a segment."""
    speaker: str  # "shreyansh", "shivangi", or "unknown"
    confidence: float  # 0.0 to 1.0
    pitch_distance: float
    spectral_distance: float
    details: Dict

    @property
    def is_unknown(self) -> bool:
        return self.speaker == "unknown"


class SpeakerIdentifier:
    """
    Stage 3: Speaker identification using calibrated voice profiles.
    Uses pitch (F0) and spectral features for matching.
    """

    def __init__(self, config: Config):
        self.config = config

        # Load voice profiles
        self.profiles: Dict[str, SpeakerProfile] = {}
        self._load_profiles()

        logger.info(f"SpeakerIdentifier initialized with {len(self.profiles)} profiles")

    def _load_profiles(self):
        """Load calibrated voice profiles from config."""
        calibration_path = self.config.speaker.calibration_file

        if Path(calibration_path).exists():
            self.profiles = load_voice_profiles(calibration_path)
            logger.info(f"Loaded profiles from {calibration_path}: {list(self.profiles.keys())}")
        else:
            logger.warning(f"Calibration file not found: {calibration_path}")
            # Use config defaults
            self.profiles = self.config.speaker.profiles

    def extract_segment_features(self, audio: np.ndarray, sr: int = 16000) -> Dict:
        """
        Extract voice features from a speech segment.
        Returns pitch and spectral centroid statistics.
        """
        import librosa

        # Ensure mono
        if audio.ndim == 2:
            audio = audio[:, 0]

        features = {}

        # Extract pitch using pyin
        try:
            f0, voiced_flags, voiced_probs = librosa.pyin(
                audio,
                fmin=librosa.note_to_hz('C2'),
                fmax=librosa.note_to_hz('C7'),
                sr=sr,
                hop_length=512
            )

            voiced_f0 = f0[~np.isnan(f0)]

            if len(voiced_f0) > 5:  # Need minimum frames for reliable estimate
                features['pitch_mean'] = float(np.mean(voiced_f0))
                features['pitch_std'] = float(np.std(voiced_f0))
                features['pitch_voiced_ratio'] = float(np.sum(~np.isnan(f0)) / len(f0))
            else:
                features['pitch_mean'] = 0.0
                features['pitch_std'] = 0.0
                features['pitch_voiced_ratio'] = 0.0

        except Exception as e:
            logger.debug(f"Pitch extraction failed: {e}")
            features['pitch_mean'] = 0.0
            features['pitch_std'] = 0.0
            features['pitch_voiced_ratio'] = 0.0

        # Extract spectral centroid
        try:
            centroids = librosa.feature.spectral_centroid(y=audio, sr=sr, hop_length=512)[0]
            features['spectral_centroid_mean'] = float(np.mean(centroids))
            features['spectral_centroid_std'] = float(np.std(centroids))
        except Exception as e:
            logger.debug(f"Spectral centroid extraction failed: {e}")
            features['spectral_centroid_mean'] = 0.0
            features['spectral_centroid_std'] = 0.0

        return features

    def compute_match_score(
        self,
        features: Dict,
        profile: SpeakerProfile
    ) -> Tuple[float, Dict]:
        """
        Compute match score between extracted features and a voice profile.
        Returns a score (higher = better match) and details.
        """
        # Calculate z-scores for pitch and spectral centroid
        details = {}

        # Pitch matching
        pitch_mean = features.get('pitch_mean', 0)
        if pitch_mean > 0 and profile.pitch_std > 0:
            pitch_z = abs(pitch_mean - profile.pitch_mean) / profile.pitch_std
            details['pitch_z'] = pitch_z
            details['pitch_mean'] = pitch_mean
        else:
            pitch_z = float('inf')
            details['pitch_z'] = float('inf')

        # Spectral centroid matching
        sc_mean = features.get('spectral_centroid_mean', 0)
        if sc_mean > 0 and profile.spectral_centroid_std > 0:
            sc_z = abs(sc_mean - profile.spectral_centroid_mean) / profile.spectral_centroid_std
            details['spectral_z'] = sc_z
            details['spectral_centroid_mean'] = sc_mean
        else:
            sc_z = float('inf')
            details['spectral_z'] = float('inf')

        # Combined score (weighted average)
        # Lower z-scores = better match
        # We use inverse distance as the score
        if pitch_z == float('inf') or sc_z == float('inf'):
            score = 0.0
        else:
            # Weight pitch more heavily (it's more speaker-specific)
            combined_z = 0.7 * pitch_z + 0.3 * sc_z
            # Convert to a score in [0, 1]
            # z < threshold_multiplier => score > 0.5
            score = max(0, 1.0 - combined_z / (2 * profile.threshold_multiplier))

        return score, details

    def identify_speaker(
        self,
        segment: SpeechSegment,
        return_features: bool = False
    ) -> SpeakerMatch:
        """
        Identify the speaker for a speech segment.

        Args:
            segment: SpeechSegment with audio data
            return_features: If True, include extracted features in details

        Returns:
            SpeakerMatch with speaker label and confidence
        """
        import time
        start_time = time.time()

        # Extract features from segment
        features = self.extract_segment_features(segment.audio, segment.sample_rate)

        # Check if we have valid features
        if features.get('pitch_voiced_ratio', 0) < 0.1:
            # Too little voiced audio - return unknown
            log_stage("SpeakerID", f"Segment too short/unvoiced: {segment.duration_seconds:.2f}s")
            return SpeakerMatch(
                speaker="unknown",
                confidence=0.0,
                pitch_distance=float('inf'),
                spectral_distance=float('inf'),
                details={"reason": "insufficient_voiced_audio"}
            )

        # Match against each profile
        best_match = None
        best_score = 0.0
        match_details = {}

        for name, profile in self.profiles.items():
            score, details = self.compute_match_score(features, profile)

            log_metric("SpeakerID", f"{name}_score", score)

            if score > best_score:
                best_score = score
                best_match = name
                match_details = {
                    'profile': name,
                    'details': details
                }

        # Determine final label
        threshold = 0.5  # Minimum confidence to accept match

        if best_match and best_score >= threshold:
            # Check if we're within the threshold multiplier
            profile = self.profiles[best_match]
            pitch_z = match_details['details'].get('pitch_z', float('inf'))

            if pitch_z <= profile.threshold_multiplier:
                speaker = best_match
                confidence = best_score
            else:
                # Outside threshold - mark as unknown
                speaker = "unknown"
                confidence = 1.0 - best_score
        else:
            speaker = "unknown"
            confidence = 1.0 - best_score

        # Add extracted features to details if requested
        if return_features:
            match_details['extracted_features'] = features

        log_metric("SpeakerID", "identification_time", time.time() - start_time, "s")

        log_stage("SpeakerID", f"Segment: {segment.duration_seconds:.2f}s -> {speaker} ({confidence:.2f})")

        return SpeakerMatch(
            speaker=speaker,
            confidence=confidence,
            pitch_distance=match_details['details'].get('pitch_z', float('inf')),
            spectral_distance=match_details['details'].get('spectral_z', float('inf')),
            details=match_details
        )

    def identify_speakers_batch(
        self,
        segments: list
    ) -> list:
        """
        Identify speakers for multiple segments.
        """
        results = []
        for segment in segments:
            match = self.identify_speaker(segment)
            results.append(match)
        return results


def test_speaker_id(audio_path: str, config_path: str = None):
    """Test speaker identification on an audio file."""
    from ..vad.silero_vad import VADProcessor
    from ..config.settings import Config
    from datetime import datetime

    print(f"\nTesting speaker identification on: {audio_path}")

    # Load config
    if config_path:
        config = Config.from_yaml(config_path)
    else:
        config = Config()

    # Initialize VAD and Speaker ID
    vad_processor = VADProcessor(config)
    speaker_id = SpeakerIdentifier(config)

    # Load and process audio
    import librosa
    audio, sr = librosa.load(audio_path, sr=16000, mono=True)

    # Get speech segments
    segments = vad_processor.process_audio_chunk(audio, datetime.now())
    print(f"\nFound {len(segments)} speech segments")

    # Identify speakers
    for i, segment in enumerate(segments, 1):
        match = speaker_id.identify_speaker(segment, return_features=True)
        print(f"\nSegment {i}:")
        print(f"  Duration: {segment.duration_seconds:.2f}s")
        print(f"  Speaker: {match.speaker}")
        print(f"  Confidence: {match.confidence:.2f}")
        if 'extracted_features' in match.details:
            feat = match.details['extracted_features']
            print(f"  Pitch: {feat.get('pitch_mean', 0):.1f} Hz")
            print(f"  Spectral: {feat.get('spectral_centroid_mean', 0):.1f} Hz")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_speaker_id(sys.argv[1])
    else:
        print("Usage: python -m voice_journal.speaker_id <audio_file>")
