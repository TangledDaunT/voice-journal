"""
Embedding-based Speaker Identification (Fix 6).
Replaces fragile pitch-threshold method with robust speaker embeddings.
"""

import numpy as np
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from pathlib import Path
import json

from config.settings import Config
from vad.silero_vad import SpeechSegment
from utils.logger import logger, log_stage, log_metric


@dataclass
class SpeakerEmbedding:
    """Speaker embedding profile."""
    name: str
    embedding: np.ndarray
    samples_count: int = 1
    samples_duration: float = 0.0


@dataclass
class SpeakerMatch:
    """Result of speaker matching."""
    speaker: str  # "shreyansh", "shivangi", or "unknown"
    confidence: float  # Similarity score
    similarity: float  # Raw cosine similarity
    details: Dict

    @property
    def is_unknown(self) -> bool:
        return self.speaker == "unknown"


class EmbeddingSpeakerIdentifier:
    """
    Speaker identification using voice embeddings.
    Replaces the fragile F0/pitch-threshold method.

    Uses cosine similarity against stored reference embeddings.
    """

    def __init__(self, config: Config):
        self.config = config

        # Similarity threshold for matching
        self.similarity_threshold = getattr(
            config.speaker,
            "embedding_similarity_threshold",
            0.75
        )

        # Reference embeddings
        self.embeddings: Dict[str, SpeakerEmbedding] = {}

        # Lazy-load embedding model
        self._encoder = None

        self._load_profiles()

        logger.info(
            f"EmbeddingSpeakerIdentifier initialized: "
            f"threshold={self.similarity_threshold}, "
            f"profiles={list(self.embeddings.keys())}"
        )

    def _load_encoder(self):
        """Lazy-load the speaker encoder model."""
        if self._encoder is not None:
            return

        # Try resemblyzer first (lightweight, CPU-friendly)
        try:
            from resemblyzer import VoiceEncoder, preprocess_wav
            self._encoder = VoiceEncoder()
            self._preprocess = preprocess_wav
            self._encoder_name = "resemblyzer"
            logger.info("Loaded resemblyzer voice encoder")
            return
        except ImportError:
            logger.debug("resemblyzer not available, trying alternatives...")

        # Fallback: use speechbrain (heavier but more accurate)
        try:
            from speechbrain.inference.speaker import SpeakerRecognition
            self._encoder = SpeakerRecognition.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="pretrained_models/spkrec-ecapa-voxceleb"
            )
            self._preprocess = None
            self._encoder_name = "speechbrain"
            logger.info("Loaded speechbrain speaker encoder")
            return
        except ImportError:
            logger.warning("speechbrain not available")

        # Final fallback: use librosa + simple MFCC features
        logger.warning(
            "No speaker encoder library found. "
            "Install resemblyzer: pip install resemblyzer"
        )
        self._encoder = None
        self._encoder_name = None

    def _load_profiles(self):
        """Load stored speaker embedding profiles."""
        calibration_path = self.config.speaker.calibration_file

        if not Path(calibration_path).exists():
            logger.warning(f"No calibration file at {calibration_path}")
            return

        try:
            with open(calibration_path, "r") as f:
                data = json.load(f)

            for name, profile in data.items():
                if "embedding" in profile:
                    embedding = np.array(profile["embedding"])
                    self.embeddings[name] = SpeakerEmbedding(
                        name=name,
                        embedding=embedding,
                        samples_count=profile.get("samples_count", 1),
                        samples_duration=profile.get("samples_duration", 0.0)
                    )
                    logger.info(f"Loaded embedding for {name}")

        except Exception as e:
            logger.error(f"Failed to load profiles: {e}")

    def compute_embedding(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        """
        Compute speaker embedding for audio.

        Args:
            audio: Audio samples
            sample_rate: Sample rate

        Returns:
            Embedding vector
        """
        self._load_encoder()

        if self._encoder is None:
            # Fallback: use MFCC mean as pseudo-embedding
            return self._compute_mfcc_embedding(audio, sample_rate)

        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Ensure mono
        if audio.ndim == 2:
            audio = audio[:, 0]

        # Normalize
        audio = audio / (np.max(np.abs(audio)) + 1e-8)

        if self._encoder_name == "resemblyzer":
            # Resemblyzer expects 16kHz
            self._encoder

            # Encode
            embedding = self._encoder.embed_utterance(audio)
            return embedding

        elif self._encoder_name == "speechbrain":
            # Speechbrain encoder
            import torch

            audio_tensor = torch.from_numpy(audio).unsqueeze(0)
            embedding = self._encoder.encode_batch(audio_tensor)
            return embedding.squeeze().numpy()

        else:
            return self._compute_mfcc_embedding(audio, sample_rate)

    def _compute_mfcc_embedding(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Fallback MFCC-based embedding (no ML library)."""
        import librosa

        # Extract MFCCs
        mfcc = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=20)

        # Use mean and std as embedding
        mean = np.mean(mfcc, axis=1)
        std = np.std(mfcc, axis=1)

        embedding = np.concatenate([mean, std])

        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def identify_speaker(
        self,
        segment: SpeechSegment,
        return_embedding: bool = False
    ) -> SpeakerMatch:
        """
        Identify speaker for a speech segment.

        Args:
            segment: SpeechSegment with audio
            return_embedding: Include computed embedding in details

        Returns:
            SpeakerMatch with speaker label and confidence
        """
        import time
        start_time = time.time()

        # Check minimum duration
        if segment.duration_seconds < 0.5:
            return SpeakerMatch(
                speaker="unknown",
                confidence=0.0,
                similarity=0.0,
                details={"reason": "segment_too_short"}
            )

        # Compute embedding
        try:
            embedding = self.compute_embedding(segment.audio, segment.sample_rate)
        except Exception as e:
            logger.error(f"Embedding computation failed: {e}")
            return SpeakerMatch(
                speaker="unknown",
                confidence=0.0,
                similarity=0.0,
                details={"reason": "embedding_failed", "error": str(e)}
            )

        # Compare against all registered speakers
        best_match = None
        best_similarity = -1.0

        for name, profile in self.embeddings.items():
            similarity = self._cosine_similarity(embedding, profile.embedding)

            log_metric("SpeakerID", f"{name}_similarity", similarity)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = name

        # Determine if match is confident enough
        if best_match and best_similarity >= self.similarity_threshold:
            # Confident match
            confidence = self._similarity_to_confidence(best_similarity)

            details = {
                "matched_profile": best_match,
                "similarity": float(best_similarity),
                "threshold": self.similarity_threshold
            }

            if return_embedding:
                details["embedding"] = embedding.tolist()

            log_stage("SpeakerID", f"→ {best_match} ({confidence:.2f})")
            log_metric("SpeakerID", "identification_time", time.time() - start_time, "s")

            return SpeakerMatch(
                speaker=best_match,
                confidence=confidence,
                similarity=best_similarity,
                details=details
            )

        else:
            # Unknown speaker
            details = {
                "reason": "below_threshold",
                "best_similarity": float(best_similarity),
                "threshold": self.similarity_threshold
            }

            if best_match:
                details["closest_match"] = best_match

            if return_embedding:
                details["embedding"] = embedding.tolist()

            log_stage("SpeakerID", f"→ unknown (sim={best_similarity:.2f})")
            log_metric("SpeakerID", "identification_time", time.time() - start_time, "s")

            return SpeakerMatch(
                speaker="unknown",
                confidence=0.0,
                similarity=best_similarity,
                details=details
            )

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        # Normalize
        a_norm = a / (np.linalg.norm(a) + 1e-8)
        b_norm = b / (np.linalg.norm(b) + 1e-8)

        return float(np.dot(a_norm, b_norm))

    def _similarity_to_confidence(self, similarity: float) -> float:
        """Convert similarity to confidence (0-1)."""
        # Map threshold->1.0 to 1.0->0.5
        # i.e., similarity at threshold = 0.5 confidence
        # similarity approaching 1.0 = approaching 1.0 confidence

        if similarity >= 1.0:
            return 1.0

        threshold = self.similarity_threshold

        if similarity <= threshold:
            return 0.0

        # Linear mapping from (threshold, 1.0) to (0.5, 1.0)
        return 0.5 + (similarity - threshold) / (2 * (1.0 - threshold))

    def register_speaker(
        self,
        name: str,
        audio: np.ndarray,
        sample_rate: int = 16000
    ):
        """
        Register a new speaker from audio sample.

        Args:
            name: Speaker name
            audio: Audio samples (30-60 seconds recommended)
            sample_rate: Sample rate
        """
        embedding = self.compute_embedding(audio, sample_rate)

        # If speaker already exists, average embeddings
        if name in self.embeddings:
            existing = self.embeddings[name]
            # Weighted average by sample count
            total_count = existing.samples_count + 1
            weight = existing.samples_count / total_count

            new_embedding = weight * existing.embedding + (1 - weight) * embedding
            new_embedding = new_embedding / np.linalg.norm(new_embedding)

            self.embeddings[name] = SpeakerEmbedding(
                name=name,
                embedding=new_embedding,
                samples_count=total_count,
                samples_duration=existing.samples_duration + len(audio) / sample_rate
            )

        else:
            self.embeddings[name] = SpeakerEmbedding(
                name=name,
                embedding=embedding,
                samples_count=1,
                samples_duration=len(audio) / sample_rate
            )

        logger.info(f"Registered speaker: {name}")

    def save_profiles(self, output_path: str = None):
        """Save speaker profiles to JSON."""
        if output_path is None:
            output_path = self.config.speaker.calibration_file

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for name, profile in self.embeddings.items():
            data[name] = {
                "embedding": profile.embedding.tolist(),
                "samples_count": profile.samples_count,
                "samples_duration": profile.samples_duration,
                "registered_at": str(np.datetime64('now'))
            }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved profiles to {output_path}")


def calibrate_embedding_speaker_id(
    audio_files: Dict[str, str],
    output_path: str,
    config: Config = None
):
    """
    Calibrate speaker ID from audio files.

    Args:
        audio_files: Dict of speaker_name -> audio_file_path
        output_path: Where to save the profiles
        config: Optional config
    """
    import librosa

    if config is None:
        config = Config()

    identifier = EmbeddingSpeakerIdentifier(config)

    for name, audio_path in audio_files.items():
        print(f"\nProcessing {name}: {audio_path}")

        # Load audio
        audio, sr = librosa.load(audio_path, sr=16000, mono=True)
        print(f"  Duration: {len(audio)/sr:.1f}s")

        # Register
        identifier.register_speaker(name, audio, sr)
        print(f"  Registered ✓")

    # Save
    identifier.save_profiles(output_path)
    print(f"\nProfiles saved to: {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Calibrate embedding-based speaker ID")
    parser.add_argument("--shreyansh", required=True, help="Audio file for Shreyansh")
    parser.add_argument("--shivangi", required=True, help="Audio file for Shivangi")
    parser.add_argument("--output", "-o", default="./config/voice_profiles.json")
    args = parser.parse_args()

    audio_files = {
        "shreyansh": args.shreyansh,
        "shivangi": args.shivangi
    }

    calibrate_embedding_speaker_id(audio_files, args.output)
