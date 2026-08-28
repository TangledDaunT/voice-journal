#!/usr/bin/env python3
"""
Integration test for the Voice Journal system.
Tests the configuration loading and basic module initialization.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import time
from datetime import datetime


def test_config():
    """Test configuration loading."""
    print("\n" + "="*60)
    print("TEST 1: Configuration Loading")
    print("="*60)

    from config.settings import Config

    config = Config()
    print(f"✓ Audio sample rate: {config.audio.sample_rate} Hz")
    print(f"✓ VAD threshold: {config.vad.threshold}")
    print(f"✓ ASR model: {config.asr.model_size}")
    print(f"✓ LLM model: {config.llm.model}")

    assert config.audio.sample_rate == 16000
    assert 0.0 <= config.vad.threshold <= 1.0

    print("\n✅ Config test PASSED")
    return config


def test_module_imports():
    """Test all module imports."""
    print("\n" + "="*60)
    print("TEST 2: Module Imports")
    print("="*60)

    modules = []

    from audio_capture.capture import AudioCapture, RingBuffer
    print("✓ AudioCapture imported")
    modules.append("AudioCapture")

    from vad.silero_vad import VADProcessor, SpeechSegment
    print("✓ VADProcessor imported")
    modules.append("VADProcessor")

    from speaker_id.identification import SpeakerIdentifier, SpeakerMatch
    print("✓ SpeakerIdentifier imported")
    modules.append("SpeakerIdentifier")

    from asr.transcriber import ASRProcessor, TranscriptSegment
    print("✓ ASRProcessor imported")
    modules.append("ASRProcessor")

    from conversation.grouping import ConversationGrouper, ConversationUnit
    print("✓ ConversationGrouper imported")
    modules.append("ConversationGrouper")

    from llm_output.classifier import LLMClassifier, ClassificationResult
    print("✓ LLMClassifier imported")
    modules.append("LLMClassifier")

    from obsidian.output import ObsidianWriter
    print("✓ ObsidianWriter imported")
    modules.append("ObsidianWriter")

    from storage.database import SQLiteStore
    print("✓ SQLiteStore imported")
    modules.append("SQLiteStore")

    print(f"\n✅ All {len(modules)} modules imported successfully")
    return modules


def test_database():
    """Test SQLite database initialization."""
    print("\n" + "="*60)
    print("TEST 3: Database Initialization")
    print("="*60)

    from config.settings import Config
    from storage.database import SQLiteStore
    import tempfile
    import os

    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config()
        config.database.path = os.path.join(tmpdir, "test.db")

        store = SQLiteStore(config)
        print(f"✓ Database created at: {config.database.path}")

        # Test stats query
        stats = store.get_stats(days=7)
        print(f"✓ Stats query successful: {stats}")

        print("\n✅ Database test PASSED")


def test_conversation_grouper():
    """Test conversation grouping logic."""
    print("\n" + "="*60)
    print("TEST 4: Conversation Grouping")
    print("="*60)

    from config.settings import Config
    from conversation.grouping import ConversationGrouper, ConversationUnit
    from asr.transcriber import TranscriptSegment
    from datetime import datetime

    config = Config()
    grouper = ConversationGrouper(config)

    print(f"✓ ConversationGrouper initialized")
    print(f"  - Gap threshold: {config.conversation.gap_seconds}s")

    # Create test transcript segments
    now = datetime.now()

    seg1 = TranscriptSegment(
        text="Hello there",
        start_time=now,
        end_time=now,
        duration_seconds=2.0,
        language="en",
        language_probability=0.95,
        speaker="shreyansh",
        speaker_confidence=0.9,
        words=[],
        segmentation_id=0
    )

    # Test that grouper starts empty
    assert grouper.pending_segments == []
    print("✓ Grouper initialization correct")

    print("\n✅ Conversation grouper test PASSED")


def test_ring_buffer():
    """Test audio ring buffer."""
    print("\n" + "="*60)
    print("TEST 5: Ring Buffer")
    print("="*60)

    from audio_capture.capture import RingBuffer
    import numpy as np

    buffer = RingBuffer(sample_rate=16000, max_seconds=5, channels=1)

    print(f"✓ Ring buffer created: {buffer.max_samples} samples")

    # Write some audio
    test_audio = np.random.randn(16000, 1).astype(np.float32) * 0.1
    buffer.write(test_audio)

    print(f"✓ Wrote 1 second of audio")

    # Read it back
    read_audio = buffer.read_last(1.0)

    assert read_audio.shape[0] == 16000
    print(f"✓ Read back 1 second: {read_audio.shape[0]} samples")

    print("\n✅ Ring buffer test PASSED")


def main():
    """Run all integration tests."""
    print("\n" + "🎤" * 30)
    print("VOICE JOURNAL - INTEGRATION TESTS")
    print("🎤" * 30)

    start_time = time.time()

    try:
        test_config()
        test_module_imports()
        test_database()
        test_conversation_grouper()
        test_ring_buffer()

        elapsed = time.time() - start_time

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print(f"Total time: {elapsed:.2f}s")
        print()

        return 0

    except Exception as e:
        print("\n" + "="*60)
        print("❌ TEST FAILED")
        print("="*60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
