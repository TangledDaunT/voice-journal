"""
Stage 5: Conversation Grouping.
Groups VAD segments into conversation units based on silence gaps.
Implements rule-based media detection.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict

from ..config.settings import Config
from ..asr.transcriber import TranscriptSegment
from ..utils.logger import logger, log_stage, log_metric


@dataclass
class ConversationUnit:
    """
    A grouped conversation unit containing multiple transcript segments.
    Represents a single "exchange" for the purpose of classification.
    """
    conversation_id: int
    start_time: datetime
    end_time: datetime
    transcript_segments: List[TranscriptSegment]
    participants: Set[str] = field(default_factory=set)
    languages: Set[str] = field(default_factory=set)
    detected_languages: List[Tuple[str, float]] = field(default_factory=list)

    # Pre-flag for media detection (from Stage 5 rules)
    preflag_source_type: str = "live_conversation"  # or "media_or_unknown"
    preflag_unknown_ratio: float = 0.0
    preflag_rapid_alternation: bool = False

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    @property
    def total_word_count(self) -> int:
        return sum(seg.word_count for seg in self.transcript_segments)

    @property
    def full_transcript(self) -> str:
        """Get formatted transcript with speaker tags."""
        lines = []
        for seg in self.transcript_segments:
            timestamp = seg.start_time.strftime("%H:%M:%S")
            speaker = seg.speaker.capitalize()
            lines.append(f"[{timestamp}] {speaker}: {seg.text}")
        return "\n".join(lines)

    @property
    def transcript_text(self) -> str:
        """Get plain transcript text."""
        return " ".join(seg.text for seg in self.transcript_segments)


class ConversationGrouper:
    """
    Stage 5: Groups transcript segments into conversation units.
    Uses silence gap threshold to determine conversation boundaries.
    Implements rule-based media detection.
    """

    def __init__(self, config: Config):
        self.config = config
        self.gap_threshold_seconds = config.conversation.gap_seconds
        self.min_segments = config.conversation.min_segments
        self.unknown_voice_threshold = config.conversation.unknown_voice_ratio_threshold
        self.rapid_alternation_threshold = config.conversation.rapid_alternation_threshold

        self.conversation_counter = 0
        self.pending_segments: List[TranscriptSegment] = []
        self.last_segment_time: Optional[datetime] = None

        logger.info(f"ConversationGrouper initialized: gap={self.gap_threshold_seconds}s")

    def add_segment(self, segment: TranscriptSegment) -> Optional[ConversationUnit]:
        """
        Add a transcript segment and check if a conversation is complete.

        Returns:
            ConversationUnit if a conversation is complete, None otherwise
        """
        now = datetime.now()

        # Check if this segment starts a new conversation
        if self.last_segment_time:
            gap = (segment.start_time - self.last_segment_time).total_seconds()

            if gap > self.gap_threshold_seconds:
                # Gap too large - finalize current conversation
                if self.pending_segments:
                    conversation = self._create_conversation()
                    self.pending_segments = []
                    # Queue new segment for next conversation
                    self.pending_segments.append(segment)
                    self.last_segment_time = segment.end_time
                    return conversation

        # Add to pending
        self.pending_segments.append(segment)
        self.last_segment_time = segment.end_time

        return None

    def flush(self) -> Optional[ConversationUnit]:
        """Flush any pending segments into a conversation."""
        if self.pending_segments:
            conversation = self._create_conversation()
            self.pending_segments = []
            return conversation
        return None

    def _create_conversation(self) -> ConversationUnit:
        """Create a conversation unit from pending segments."""
        self.conversation_counter += 1

        if not self.pending_segments:
            raise ValueError("No segments to create conversation")

        # Time bounds
        start_time = self.pending_segments[0].start_time
        end_time = self.pending_segments[-1].end_time

        # Collect participants
        participants = set(seg.speaker for seg in self.pending_segments)

        # Collect languages
        languages = set()
        lang_probs = defaultdict(list)
        for seg in self.pending_segments:
            languages.add(seg.language)
            lang_probs[seg.language].append(seg.language_probability)

        # Average language probabilities
        lang_list = [(lang, sum(probs)/len(probs)) for lang, probs in lang_probs.items()]
        lang_list.sort(key=lambda x: x[1], reverse=True)

        conversation = ConversationUnit(
            conversation_id=self.conversation_counter,
            start_time=start_time,
            end_time=end_time,
            transcript_segments=self.pending_segments.copy(),
            participants=participants,
            languages=languages,
            detected_languages=lang_list
        )

        # Apply rule-based media detection
        self._apply_media_detection(conversation)

        log_stage("Conversation", f"Created #{conversation.conversation_id}: "
                   f"{len(conversation.transcript_segments)} segments, "
                   f"{conversation.duration_seconds:.1f}s, "
                   f"participants={conversation.participants}, "
                   f"preflag={conversation.preflag_source_type}")

        return conversation

    def _apply_media_detection(self, conversation: ConversationUnit):
        """
        Apply rule-based media detection pre-flagging.
        This provides a signal that Stage 6 (LLM) should respect/refine.
        """
        # Calculate unknown voice ratio
        segments = conversation.transcript_segments
        unknown_count = sum(1 for seg in segments if seg.speaker == "unknown")
        unknown_ratio = unknown_count / len(segments) if segments else 0

        conversation.preflag_unknown_ratio = unknown_ratio

        # Check for rapid alternation between speakers
        rapid_alternation = self._detect_rapid_alternation(segments)
        conversation.preflag_rapid_alternation = rapid_alternation

        # Apply rules
        if unknown_ratio >= self.unknown_voice_threshold:
            # High unknown ratio -> likely media
            conversation.preflag_source_type = "media_or_unknown"
            log_stage("Conversation", f"  → Flagged as media: unknown_ratio={unknown_ratio:.2f}")

        elif rapid_alternation and unknown_ratio > 0.3:
            # Rapid alternation with some unknown -> media
            conversation.preflag_source_type = "media_or_unknown"
            log_stage("Conversation", f"  → Flagged as media: rapid alternation + unknown")

        elif "unknown" in conversation.participants and len(conversation.participants) == 1:
            # Only unknown speaker, no Shivangi or Shreyansh
            conversation.preflag_source_type = "media_or_unknown"
            log_stage("Conversation", f"  → Flagged as media: only unknown speaker")

        else:
            conversation.preflag_source_type = "live_conversation"

    def _detect_rapid_alternation(self, segments: List[TranscriptSegment]) -> bool:
        """
        Detect rapid alternation between speakers (typical of media).
        Returns True if speakers alternate more than N times with short gaps.
        """
        if len(segments) < 3:
            return False

        alternation_count = 0
        last_speaker = None

        for seg in segments:
            if last_speaker and seg.speaker != last_speaker:
                alternation_count += 1
            last_speaker = seg.speaker

        # If many alternations relative to segment count
        alternation_ratio = alternation_count / len(segments) if segments else 0
        return alternation_ratio > 0.5

    def group_segments(
        self,
        segments: List[TranscriptSegment]
    ) -> List[ConversationUnit]:
        """
        Group a batch of transcript segments into conversations.
        This is for batch processing (e.g., testing with pre-recorded audio).
        """
        conversations = []
        self.pending_segments = []
        self.last_segment_time = None

        for segment in segments:
            conv = self.add_segment(segment)
            if conv:
                conversations.append(conv)

        # Don't forget the last conversation
        conv = self.flush()
        if conv:
            conversations.append(conv)

        return conversations


def test_grouping(audio_path: str):
    """Test conversation grouping on an audio file."""
    from datetime import datetime
    from ..config.settings import Config
    from ..vad.silero_vad import VADProcessor
    from ..speaker_id.identification import SpeakerIdentifier
    from ..asr.transcriber import ASRProcessor
    import librosa

    print(f"\nTesting conversation grouping on: {audio_path}")

    config = Config()
    vad_processor = VADProcessor(config)
    speaker_id = SpeakerIdentifier(config)
    asr = ASRProcessor(config)
    grouper = ConversationGrouper(config)

    # Load and process
    audio, sr = librosa.load(audio_path, sr=16000, mono=True)
    segments = vad_processor.process_audio_chunk(audio, datetime.now())

    print(f"\nFound {len(segments)} speech segments")

    # Identify and transcribe
    transcript_segments = []
    for i, segment in enumerate(segments):
        speaker_match = speaker_id.identify_speaker(segment)
        transcript = asr.transcribe_with_timing(segment, speaker_match, i)
        if transcript:
            transcript_segments.append(transcript)

    # Group
    conversations = grouper.group_segments(transcript_segments)

    print(f"\n{len(conversations)} conversations detected:")
    for conv in conversations:
        print(f"\n{'='*60}")
        print(f"Conversation #{conv.conversation_id}")
        print(f"  Duration: {conv.duration_seconds:.1f}s")
        print(f"  Participants: {conv.participants}")
        print(f"  Languages: {conv.languages}")
        print(f"  Pre-flag: {conv.preflag_source_type}")
        print(f"  Unknown ratio: {conv.preflag_unknown_ratio:.2f}")
        print(f"  Word count: {conv.total_word_count}")
        print(f"\nTranscript:")
        print(conv.full_transcript)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_grouping(sys.argv[1])
    else:
        print("Usage: python -m voice_journal.conversation <audio_file>")
