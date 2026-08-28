"""
Calibration script for voice profiles.
Records or loads audio samples for Shreyansh and Shivangi,
extracts pitch and spectral features, and saves profiles.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional, Tuple
import warnings

import numpy as np

# Suppress warnings from librosa
warnings.filterwarnings("ignore", message="PySoundFile failed.*")


@dataclass
class VoiceProfile:
    """Voice profile containing extracted features."""
    name: str
    pitch_mean: float
    pitch_std: float
    pitch_range: Tuple[float, float]
    spectral_centroid_mean: float
    spectral_centroid_std: float
    spectral_centroid_range: Tuple[float, float]
    mfcc_mean: np.ndarray
    threshold_multiplier: float = 2.0

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "pitch_mean": float(self.pitch_mean),
            "pitch_std": float(self.pitch_std),
            "pitch_range": [float(self.pitch_range[0]), float(self.pitch_range[1])],
            "spectral_centroid_mean": float(self.spectral_centroid_mean),
            "spectral_centroid_std": float(self.spectral_centroid_std),
            "spectral_centroid_range": [float(self.spectral_centroid_range[0]),
                                         float(self.spectral_centroid_range[1])],
            "mfcc_mean": self.mfcc_mean.tolist() if isinstance(self.mfcc_mean, np.ndarray) else self.mfcc_mean,
            "threshold_multiplier": float(self.threshold_multiplier)
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "VoiceProfile":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            pitch_mean=data["pitch_mean"],
            pitch_std=data["pitch_std"],
            pitch_range=tuple(data["pitch_range"]),
            spectral_centroid_mean=data["spectral_centroid_mean"],
            spectral_centroid_std=data["spectral_centroid_std"],
            spectral_centroid_range=tuple(data["spectral_centroid_range"]),
            mfcc_mean=np.array(data["mfcc_mean"]),
            threshold_multiplier=data.get("threshold_multiplier", 2.0)
        )


def load_audio(audio_path: str, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
    """Load audio file using available library."""
    import librosa

    # Load audio (mono, resampled)
    audio, sr = librosa.load(audio_path, sr=target_sr, mono=True)
    return audio, sr


def extract_pitch(audio: np.ndarray, sr: int = 16000) -> Tuple[np.ndarray, Dict]:
    """
    Extract fundamental frequency (F0) using librosa.pyin.
    Returns voiced F0 values and statistics.
    """
    import librosa

    # pyin: probabilistic YIN algorithm for F0 estimation
    f0, voiced_flags, voiced_probs = librosa.pyin(
        audio,
        fmin=librosa.note_to_hz('C2'),  # ~65 Hz (deep male)
        fmax=librosa.note_to_hz('C7'),  # ~2093 Hz (high female)
        sr=sr,
        hop_length=512
    )

    # Filter to voiced frames only
    voiced_f0 = f0[~np.isnan(f0)]

    if len(voiced_f0) == 0:
        # Fallback: no voiced frames detected
        return np.array([]), {
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "max": 0.0,
            "voiced_ratio": 0.0
        }

    stats = {
        "mean": float(np.mean(voiced_f0)),
        "std": float(np.std(voiced_f0)),
        "min": float(np.min(voiced_f0)),
        "max": float(np.max(voiced_f0)),
        "voiced_ratio": float(np.sum(~np.isnan(f0)) / len(f0))
    }

    return voiced_f0, stats


def extract_spectral_centroid(audio: np.ndarray, sr: int = 16000) -> Tuple[np.ndarray, Dict]:
    """
    Extract spectral centroid (brightness measure).
    Indicates where the "center of mass" of the spectrum is.
    """
    import librosa

    # Compute spectral centroid
    centroids = librosa.feature.spectral_centroid(y=audio, sr=sr, hop_length=512)[0]

    stats = {
        "mean": float(np.mean(centroids)),
        "std": float(np.std(centroids)),
        "min": float(np.min(centroids)),
        "max": float(np.max(centroids))
    }

    return centroids, stats


def extract_mfcc(audio: np.ndarray, sr: int = 16000, n_mfcc: int = 13) -> np.ndarray:
    """Extract MFCC features and return mean across frames."""
    import librosa

    mfccs = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=n_mfcc, hop_length=512)
    # Return mean across time dimension
    return np.mean(mfccs, axis=1)


def extract_voice_features(audio_path: str, name: str) -> VoiceProfile:
    """
    Extract all voice features from an audio file.
    Returns a VoiceProfile with all extracted features.
    """
    print(f"\n{'='*60}")
    print(f"Extracting features for: {name}")
    print(f"Audio file: {audio_path}")
    print(f"{'='*60}")

    # Load audio
    audio, sr = load_audio(audio_path)
    duration = len(audio) / sr
    print(f"Duration: {duration:.1f} seconds")
    print(f"Sample rate: {sr} Hz")

    # Extract pitch
    print("\nExtracting pitch (F0)...")
    f0, f0_stats = extract_pitch(audio, sr)
    print(f"  Mean F0: {f0_stats['mean']:.1f} Hz")
    print(f"  Std F0: {f0_stats['std']:.1f} Hz")
    print(f"  Range: {f0_stats['min']:.1f} - {f0_stats['max']:.1f} Hz")
    print(f"  Voiced ratio: {f0_stats['voiced_ratio']*100:.1f}%")

    # Extract spectral centroid
    print("\nExtracting spectral centroid...")
    _, centroid_stats = extract_spectral_centroid(audio, sr)
    print(f"  Mean: {centroid_stats['mean']:.1f} Hz")
    print(f"  Std: {centroid_stats['std']:.1f} Hz")

    # Extract MFCC
    print("\nExtracting MFCCs...")
    mfcc_mean = extract_mfcc(audio, sr)
    print(f"  MFCC shape: {mfcc_mean.shape}")

    # Create profile
    profile = VoiceProfile(
        name=name.lower(),
        pitch_mean=f0_stats['mean'],
        pitch_std=f0_stats['std'],
        pitch_range=(f0_stats['min'], f0_stats['max']),
        spectral_centroid_mean=centroid_stats['mean'],
        spectral_centroid_std=centroid_stats['std'],
        spectral_centroid_range=(centroid_stats['min'], centroid_stats['max']),
        mfcc_mean=mfcc_mean,
        threshold_multiplier=2.0
    )

    print(f"\n✓ Profile extracted for {name}")
    return profile


def calibrate_from_files(
    shreyansh_path: str,
    shivangi_path: str,
    output_path: str = "./config/voice_profiles.json",
    threshold_multiplier: float = 2.0
) -> Dict[str, VoiceProfile]:
    """
    Calibrate voice profiles from pre-recorded audio files.
    """

    print("\n" + "="*60)
    print("VOICE PROFILE CALIBRATION")
    print("="*60)

    # Extract features for each person
    profiles = {}

    if shreyansh_path and os.path.exists(shreyansh_path):
        profiles["shreyansh"] = extract_voice_features(shreyansh_path, "Shreyansh")
        profiles["shreyansh"].threshold_multiplier = threshold_multiplier
    else:
        print(f"\n⚠️  Shreyansh audio file not found: {shreyansh_path}")

    if shivangi_path and os.path.exists(shivangi_path):
        profiles["shivangi"] = extract_voice_features(shivangi_path, "Shivangi")
        profiles["shivangi"].threshold_multiplier = threshold_multiplier
    else:
        print(f"\n⚠️  Shivangi audio file not found: {shivangi_path}")

    if not profiles:
        print("\n❌ No voice profiles could be created!")
        return {}

    # Save profiles
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    profiles_dict = {k: v.to_dict() for k, v in profiles.items()}
    with open(output_path, "w") as f:
        json.dump(profiles_dict, f, indent=2)

    print(f"\n" + "="*60)
    print(f"✓ Voice profiles saved to: {output_path}")
    print(f"  Profiles: {list(profiles.keys())}")
    print("="*60 + "\n")

    return profiles


def main():
    """Main entry point for calibration."""
    parser = argparse.ArgumentParser(
        description="Calibrate voice profiles for speaker identification"
    )
    parser.add_argument(
        "--shreyansh",
        type=str,
        default="./calibration_shreyansh.m4a",
        help="Path to Shreyansh's voice sample (30-60 seconds)"
    )
    parser.add_argument(
        "--shivangi",
        type=str,
        default="./calibration_shivangi.m4a",
        help="Path to Shivangi's voice sample (30-60 seconds)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="./config/voice_profiles.json",
        help="Output path for voice profiles"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=2.0,
        help="Number of standard deviations for matching threshold"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive recording mode (not implemented yet)"
    )

    args = parser.parse_args()

    # Check if files exist
    if not os.path.exists(args.shreyansh):
        print(f"⚠️  File not found: {args.shreyansh}")
        print("   Please provide a voice sample for Shreyansh")

    if not os.path.exists(args.shivangi):
        print(f"⚠️  File not found: {args.shivangi}")
        print("   Please provide a voice sample for Shivangi")

    # Run calibration
    profiles = calibrate_from_files(
        shreyansh_path=args.shreyansh,
        shivangi_path=args.shivangi,
        output_path=args.output,
        threshold_multiplier=args.threshold
    )

    if profiles:
        print("\n" + "="*60)
        print("CALIBRATION COMPLETE")
        print("="*60)
        print("\nProfile Summary:")
        print("-"*60)
        for name, profile in profiles.items():
            print(f"\n{name.upper()}:")
            print(f"  Pitch: {profile.pitch_mean:.1f} ± {profile.pitch_std:.1f} Hz "
                  f"[{profile.pitch_range[0]:.0f}-{profile.pitch_range[1]:.0f}]")
            print(f"  Spectral Centroid: {profile.spectral_centroid_mean:.1f} ± "
                  f"{profile.spectral_centroid_std:.1f} Hz")
            print(f"  Match Threshold: ±{profile.threshold_multiplier} std devs")

        print("\n" + "-"*60)
        print("Next steps:")
        print("  1. Review the profile values above")
        print("  2. Adjust thresholds in config if needed")
        print("  3. Run the voice journal daemon")
        print("="*60 + "\n")

        return 0
    else:
        print("\n❌ Calibration failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
