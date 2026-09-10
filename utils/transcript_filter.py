"""
Transcript Quality Filter.
Filters and scores transcript segments for quality and meaningfulness.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from collections import Counter


@dataclass
class QualityScore:
    """Quality assessment for a transcript segment."""
    score: float  # 0.0 to 1.0
    is_garbage: bool
    is_media_artifact: bool
    is_prompt_leak: bool
    is_repetitive: bool
    is_too_short: bool
    language_mismatch: bool
    reason: str = ""


@dataclass
class FilterConfig:
    """Configuration for transcript filtering."""
    # Minimum words to consider meaningful
    min_words: int = 3

    # Repetition threshold (same word N times)
    repetition_threshold: int = 3

    # Quality score threshold below which segment is flagged
    quality_threshold: float = 0.3

    # If this fraction of segments are garbage, discard conversation
    garbage_fraction_threshold: float = 0.7

    # Known media/subtitle signatures to filter out
    media_signatures: tuple = (
        # Subtitle credits
        "thank you", "gracias", "merci", "danke", "спасибо", "谢谢",
        "terima kasih", "สวัสดี", "ধন্যবাদ", "شكرا", "ধন্যবাদ",
        "god bless", "god bless you", "amen",
        # Subtitle creator credits
        "subtitle", "subtitles", "字幕", "字幕组", "субтитры",
        "community", "amara", "addic7ed", "opensubtitles",
        "created by", "made by", "synced by", "corrected by",
        # Common YouTube/media phrases
        "subscribe", "subscription", "ดูเพิ่มเติม",
        "thanks for watching", "thank you for watching",
        "please subscribe", "like and subscribe",
        "follow me on", "check out my",
        # Intro/outro phrases
        "enjoy the video", "enjoy", "see you next time",
        "goodbye", "bye bye", "see you", "अलविदा",
        # Credits
        "directed by", "produced by", "music by",
        # Short filler phrases common in media
        "okay", "ok", "yeah", "yep", "nope",
    )

    # Whisper prompt leakage patterns
    prompt_patterns: tuple = (
        "shreyansh, shivangi",
        "use only hindi and english",
        "do not output any other language",
    )


class TranscriptFilter:
    """
    Multi-layer transcript quality filter.

    Filters out:
    1. Media artifacts (subtitle credits, YouTube intros)
    2. Whisper hallucinations (prompt leakage, repetitive text)
    3. Garbage transcription (low confidence, gibberish)
    4. Meaningless short segments
    """

    def __init__(self, config: FilterConfig = None):
        self.config = config or FilterConfig()
        self._stats = {
            "segments_processed": 0,
            "segments_filtered": 0,
            "media_artifacts": 0,
            "prompt_leaks": 0,
            "repetitive": 0,
        }

    def score_segment(self, text: str, word_count: int,
                       confidence: float = 1.0,
                       is_low_confidence: bool = False) -> QualityScore:
        """
        Score a transcript segment for quality.

        Args:
            text: The transcript text
            word_count: Number of words in segment
            confidence: Whisper confidence (if available)
            is_low_confidence: Whether Whisper flagged it as low confidence

        Returns:
            QualityScore with assessment
        """
        self._stats["segments_processed"] += 1

        text_lower = text.strip().lower()

        # Initialize flags
        is_garbage = False
        is_media_artifact = False
        is_prompt_leak = False
        is_repetitive = False
        is_too_short = False
        language_mismatch = False
        reasons = []

        # Check 1: Prompt leakage
        for pattern in self.config.prompt_patterns:
            if pattern in text_lower:
                is_prompt_leak = True
                is_garbage = True
                reasons.append("prompt_leak")
                self._stats["prompt_leaks"] += 1
                break

        # Check 2: Media artifacts
        if not is_garbage:
            for sig in self.config.media_signatures:
                if text_lower == sig or text_lower.endswith(sig):
                    is_media_artifact = True
                    is_garbage = True
                    reasons.append("media_artifact")
                    self._stats["media_artifacts"] += 1
                    break
            # Also check if it's a very short common phrase
            if word_count <= 2 and text_lower in self.config.media_signatures:
                is_media_artifact = True
                is_garbage = True
                reasons.append("short_media_phrase")

        # Check 3: Repetitive content
        if not is_garbage and word_count >= 3:
            words = text_lower.split()
            word_counts = Counter(words)
            # Check if any word appears 3+ times
            for word, count in word_counts.items():
                if count >= self.config.repetition_threshold and len(word) > 2:
                    is_repetitive = True
                    is_garbage = True
                    reasons.append(f"repetitive({word}x{count})")
                    self._stats["repetitive"] += 1
                    break

            # Also check for repeated phrases (2+ words repeated)
            if not is_repetitive:
                for i in range(len(words) - 3):
                    phrase = " ".join(words[i:i+2])
                    phrase_count = text_lower.count(phrase)
                    if phrase_count >= 3:
                        is_repetitive = True
                        is_garbage = True
                        reasons.append(f"phrase_repetition({phrase}x{phrase_count})")
                        self._stats["repetitive"] += 1
                        break

        # Check 4: Too short and meaningless
        if not is_garbage and word_count < self.config.min_words:
            # Check if it's just filler
            fillers = {"um", "uh", "ah", "hmm", "mm", "ha", "heh"}
            words_set = set(text_lower.split())
            if words_set.issubset(fillers) or word_count == 0:
                is_too_short = True
                is_garbage = True
                reasons.append("too_short_filler")

        # Check 5: Very low confidence
        if is_low_confidence and word_count < 5:
            is_garbage = True
            reasons.append("low_confidence_short")

        # Calculate quality score
        score = 1.0
        if is_garbage:
            score = 0.0
        else:
            # Penalize for various quality issues
            if is_low_confidence:
                score -= 0.3
            if word_count < 3:
                score -= 0.2
            if confidence < 0.8:
                score -= 0.2
            score = max(0.0, min(1.0, score))

        if is_garbage:
            self._stats["segments_filtered"] += 1

        return QualityScore(
            score=score,
            is_garbage=is_garbage,
            is_media_artifact=is_media_artifact,
            is_prompt_leak=is_prompt_leak,
            is_repetitive=is_repetitive,
            is_too_short=is_too_short,
            language_mismatch=language_mismatch,
            reason="; ".join(reasons) if reasons else "ok"
        )

    def filter_conversation(self, segments: List[dict]) -> Tuple[List[dict], QualityScore]:
        """
        Filter a list of segments for a conversation.

        Args:
            segments: List of segment dicts with 'text', 'word_count', etc.

        Returns:
            Tuple of (filtered_segments, overall_quality)
        """
        if not segments:
            return [], QualityScore(0.0, True, False, False, False, False, False, "no_segments")

        good_segments = []
        garbage_count = 0

        for seg in segments:
            text = seg.get("text", "")
            word_count = seg.get("word_count", len(text.split()))
            confidence = seg.get("confidence", 1.0)
            is_low_confidence = seg.get("low_confidence", False)

            quality = self.score_segment(text, word_count, confidence, is_low_confidence)

            if not quality.is_garbage:
                good_segments.append(seg)
            else:
                garbage_count += 1

        garbage_fraction = garbage_count / len(segments) if segments else 0

        # Overall quality
        overall_quality = QualityScore(
            score=1.0 - garbage_fraction,
            is_garbage=garbage_fraction >= self.config.garbage_fraction_threshold,
            is_media_artifact=any(
                self.score_segment(
                    s.get("text", ""),
                    s.get("word_count", 0)
                ).is_media_artifact
                for s in segments
            ),
            is_prompt_leak=False,
            is_repetitive=False,
            is_too_short=False,
            language_mismatch=False,
            reason=f"garbage_fraction={garbage_fraction:.2f}"
        )

        return good_segments, overall_quality

    def get_stats(self) -> dict:
        """Get filtering statistics."""
        return self._stats.copy()

    def reset_stats(self):
        """Reset filtering statistics."""
        for key in self._stats:
            self._stats[key] = 0


# Convenience function
def create_filter(config: FilterConfig = None) -> TranscriptFilter:
    """Create a transcript filter with optional config."""
    return TranscriptFilter(config)
