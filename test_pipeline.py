#!/usr/bin/env python3
"""
Test pipeline stages independently.
Useful for debugging and validation.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from voice_journal.config.settings import Config
from voice_journal.vad.silero_vad import VADProcessor
from voice_journal.speaker_id.identification import SpeakerIdentifier
from voice_journal.asr.transcriber import ASRProcessor
from voice_journal.conversation.grouping import ConversationGrouper
from voice_journal.llm_output.classifier import LLMClassifier
from voice_journal.obsidian.output import ObsidianWriter
from voice_journal.storage.database import SQLiteStore


def test_vad(audio_path: str, config: Config):
    """Test VAD stage."""
    import librosa

    print(f"\n{'='*60}")
    print("Testing VAD (Stage 2)")
    print(f"{'='*60}")

    audio, sr = librosa.load(audio_path, sr=16000, mono=True)
    print(f"Audio: {len(audio)/sr:.1f}s")

    vad = VADProcessor(config)
    segments = vad.process_audio_chunk(audio, datetime.now())

    print(f"\nDetected {len(segments)} speech segments:")
    for i, seg in enumerate(segments[:10], 1):
        print(f"  {i}. {seg.duration_seconds:.2f}s")

    return segments


def test_speaker_id(segments: list, config: Config):
    """Test Speaker ID stage."""
    print(f"\n{'='*60}")
    print("Testing Speaker ID (Stage 3)")
    print(f"{'='*60}")

    speaker_id = SpeakerIdentifier(config)
    matches = speaker_id.identify_speakers_batch(segments)

    for i, match in enumerate(matches[:10], 1):
        print(f"  {i}. {matches[i-1].speaker} (conf={match.confidence:.2f})")

    return matches


def test_asr(segments: list, matches: list, config: Config):
    """Test ASR stage."""
    print(f"\n{'='*60}")
    print("Testing ASR (Stage 4)")
    print(f"{'='*60}")

    asr = ASRProcessor(config)
    transcripts = []

    for i, (segment, match) in enumerate(zip(segments, matches)):
        print(f"\nSegment {i+1}:")
        transcript = asr.transcribe_with_timing(segment, match, i)
        if transcript:
            transcripts.append(transcript)
            print(f"  [{transcript.language}] {transcript.text[:80]}...")

    return transcripts


def test_conversation(transcripts: list, config: Config):
    """Test conversation grouping."""
    print(f"\n{'='*60}")
    print("Testing Conversation Grouping (Stage 5)")
    print(f"{'='*60}")

    grouper = ConversationGrouper(config)
    conversations = grouper.group_segments(transcripts)

    print(f"\n{len(conversations)} conversations created:")
    for conv in conversations:
        print(f"  #{conv.conversation_id}: {conv.duration_seconds:.1f}s, "
              f"participants={conv.participants}, preflag={conv.preflag_source_type}")

    return conversations


def test_llm(conversations: list, config: Config):
    """Test LLM classification."""
    print(f"\n{'='*60}")
    print("Testing LLM Classification (Stage 6)")
    print(f"{'='*60}")

    classifier = LLMClassifier(config)
    classifications = classifier.classify_batch(conversations)

    for i, classification in enumerate(classifications, 1):
        print(f"\nConversation {i}:")
        print(f"  Type: {classification.source_type}")
        print(f"  Quality: {classification.quality}")
        print(f"  With Shivangi: {classification.is_shivangi_conversation}")
        print(f"  Summary: {classification.summary[:60]}...")

    return classifications


def test_full_pipeline(audio_path: str, config: Config):
    """Run through the full pipeline."""
    import librosa

    print(f"\n{'='*60}")
    print(f"FULL PIPELINE TEST: {audio_path}")
    print(f"{'='*60}")

    # Load audio
    audio, sr = librosa.load(audio_path, sr=16000, mono=True)
    duration = len(audio) / sr
    print(f"Audio: {duration:.1f} seconds")

    # Stage 2: VAD
    segments = test_vad(audio_path, config)
    if not segments:
        print("No speech detected!")
        return

    # Stage 3: Speaker ID
    matches = test_speaker_id(segments, config)

    # Stage 4: ASR
    transcripts = test_asr(segments, matches, config)
    if not transcripts:
        print("No transcripts generated!")
        return

    # Stage 5: Conversation grouping
    conversations = test_conversation(transcripts, config)

    # Stage 6: LLM classification
    classifications = test_llm(conversations, config)

    # Stage 7 & 8: Output
    print(f"\n{'='*60}")
    print("Output Stages (7 & 8)")
    print(f"{'='*60}")

    obsidian = ObsidianWriter(config)
    sqlite = SQLiteStore(config)

    for conv, classification in zip(conversations, classifications):
        note_path = obsidian.write_conversation_note(conv, classification)
        sqlite.insert_conversation(conv, classification, note_path)

    print(f"\n✓ Pipeline test complete")


def main():
    parser = argparse.ArgumentParser(description="Test voice journal pipeline stages")
    parser.add_argument("audio_file", help="Audio file to test")
    parser.add_argument(
        "--stage", "-s",
        choices=["vad", "speaker", "asr", "conversation", "llm", "full"],
        default="full",
        help="Stage to test (default: full pipeline)"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to configuration file"
    )

    args = parser.parse_args()

    # Load config
    if args.config:
        config = Config.from_yaml(args.config)
    else:
        config = Config()

    # Run test
    if args.stage == "vad":
        test_vad(args.audio_file, config)
    elif args.stage == "full":
        test_full_pipeline(args.audio_file, config)
    else:
        # Run up to the specified stage
        import librosa
        audio, sr = librosa.load(args.audio_file, sr=16000, mono=True)

        segments = test_vad(args.audio_file, config)

        if args.stage in ["speaker", "asr", "conversation", "llm"]:
            matches = test_speaker_id(segments, config)

            if args.stage in ["asr", "conversation", "llm"]:
                transcripts = test_asr(segments, matches, config)

                if args.stage in ["conversation", "llm"]:
                    conversations = test_conversation(transcripts, config)

                    if args.stage == "llm":
                        test_llm(conversations, config)


if __name__ == "__main__":
    main()
