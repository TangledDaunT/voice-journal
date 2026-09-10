"""
Media Detection Module.
Detects and skips transcription for media playback (YouTube, Netflix, Spotify, etc.).
"""

import subprocess
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import re
import json


@dataclass
class MediaDetectionResult:
    """Result of media detection."""
    is_media: bool
    source: Optional[str] = None  # "youtube", "netflix", "spotify", "vlc", etc.
    process_name: Optional[str] = None
    confidence: float = 0.0


class MediaDetector:
    """
    Detects media playback to skip transcription.

    Methods:
    1. Process detection: Check if media apps are playing
    2. Audio fingerprinting: Match against known media audio signatures
    3. Audio pattern analysis: Detect looped/repeated content (ads, music)
    """

    # Known media application patterns
    MEDIA_PROCESSES = {
        # Streaming
        "youtube": ["youtube", "yt-dlp", "youtube-dl", "chrome.*youtube", "firefox.*youtube"],
        "netflix": ["netflix", "chrome.*netflix", "firefox.*netflix"],
        "spotify": ["spotify"],
        "prime_video": ["prime", "amazon.*video"],
        "hotstar": ["hotstar", "disney"],
        "zee5": ["zee5"],

        # Local players
        "vlc": ["vlc"],
        "mpv": ["mpv"],
        "totem": ["totem"],
        "mplayer": ["mplayer"],

        # Browsers (media in tabs)
        "chrome_media": ["chrome"],
        "firefox_media": ["firefox"],
    }

    def __init__(self, config=None):
        self.config = config
        self._recent_detections = []

    def is_media_playing(self) -> MediaDetectionResult:
        """
        Check if media is currently playing.

        Returns:
            MediaDetectionResult with detection details
        """
        try:
            # Get list of running processes
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )
            processes = result.stdout.lower()

            # Check for media processes
            for source, patterns in self.MEDIA_PROCESSES.items():
                for pattern in patterns:
                    if re.search(pattern, processes, re.IGNORECASE):
                        # Found a media process - verify it's playing
                        if self._is_actively_playing(source, processes):
                            return MediaDetectionResult(
                                is_media=True,
                                source=source,
                                confidence=0.8
                            )

            # Check PulseAudio/PipeWire for media streams
            if self._check_audio_sink_media():
                return MediaDetectionResult(
                    is_media=True,
                    source="audio_sink",
                    confidence=0.7
                )

            return MediaDetectionResult(is_media=False)

        except Exception as e:
            return MediaDetectionResult(is_media=False)

    def _is_actively_playing(self, source: str, processes: str) -> bool:
        """Check if the media source is actively playing (not just open)."""
        # For players like VLC, check state
        if source in ["vlc", "mpv"]:
            try:
                result = subprocess.run(
                    ["playerctl", "-a", "status"],
                    capture_output=True,
                    text=True
                )
                if "Playing" in result.stdout:
                    return True
            except:
                pass

        # For browsers, check if audio is being output
        if source in ["chrome_media", "firefox_media"]:
            return self._check_audio_sink_media()

        return True

    def _check_audio_sink_media(self) -> bool:
        """Check PulseAudio/PipeWire sinks for media streams."""
        try:
            # Check pactl for media role streams
            result = subprocess.run(
                ["pactl", "list", "sink-inputs"],
                capture_output=True,
                text=True
            )

            # Look for media role streams
            if "media.role = \"video\"" in result.stdout.lower():
                return True
            if "media.role = \"music\"" in result.stdout.lower():
                return True
            if "application.name" in result.stdout.lower():
                # Parse application names
                for media_app in ["youtube", "netflix", "spotify", "vlc"]:
                    if media_app in result.stdout.lower():
                        return True

        except:
            pass

        return False

    def analyze_audio_signature(self, audio: np.ndarray, sample_rate: int) -> MediaDetectionResult:
        """
        Analyze audio for media signatures.

        Detects:
        - High compression/repetition (music)
        - Stereo patterns (pre-recorded content)
        - Frequency patterns typical of music/movies
        """
        if len(audio) < sample_rate:  # Less than 1 second
            return MediaDetectionResult(is_media=False)

        # Check for high energy/steady pattern (music)
        rms = np.sqrt(np.mean(audio ** 2))

        # Check for repeating patterns (ads, songs)
        chunk_duration = 5  # seconds
        chunk_samples = chunk_duration * sample_rate

        if len(audio) > chunk_samples * 2:
            # Compare chunks for repetition
            chunks = [
                audio[i:i+chunk_samples]
                for i in range(0, len(audio) - chunk_samples, chunk_samples)
            ]

            if len(chunks) >= 2:
                # Calculate similarity between consecutive chunks
                similarities = []
                for i in range(len(chunks) - 1):
                    corr = np.corrcoef(chunks[i][:len(chunks[i+1])], chunks[i+1])[0, 1]
                    if not np.isnan(corr):
                        similarities.append(corr)

                if similarities:
                    avg_similarity = np.mean(similarities)

                    # High repetition suggests music/media
                    if avg_similarity > 0.7:
                        return MediaDetectionResult(
                            is_media=True,
                            source="repetitive_audio",
                            confidence=avg_similarity
                        )

        return MediaDetectionResult(is_media=False)

    def should_skip_transcription(
        self,
        audio: np.ndarray = None,
        sample_rate: int = 16000
    ) -> bool:
        """
        Main entry point: Should we skip transcription?

        Args:
            audio: Optional audio buffer for signature analysis
            sample_rate: Audio sample rate

        Returns:
            True if we should skip (media detected)
        """
        # First, check processes
        proc_result = self.is_media_playing()
        if proc_result.is_media and proc_result.confidence > 0.7:
            return True

        # Second, check audio signature if provided
        if audio is not None:
            sig_result = self.analyze_audio_signature(audio, sample_rate)
            if sig_result.is_media and sig_result.confidence > 0.8:
                return True

        return False
