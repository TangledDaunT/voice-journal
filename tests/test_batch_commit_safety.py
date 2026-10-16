"""A failed result commit must never acknowledge staged source audio."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conversation.grouping import ConversationGrouper
from processing.batch_processor import BatchProcessor


@pytest.mark.parametrize("commit_fails", [True, False])
def test_staging_acknowledged_only_after_commit(test_config, speech_segment, commit_fails):
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.config = test_config
    processor.storage_guard = None
    processor._init_heavy_components = Mock()
    processor.staging_queue = Mock()
    processor.staging_queue.get_pending_segments.return_value = [SimpleNamespace(segment_id="source-1")]
    processor.staging_queue.load_segment_audio.return_value = speech_segment
    unit = SimpleNamespace(
        audio=speech_segment.audio, sample_rate=speech_segment.sample_rate,
        duration_seconds=1, source_segments=[speech_segment],
    )
    processor.segment_merger = Mock()
    processor.segment_merger.add_segments_batch.return_value = [unit]
    processor.preprocessor = Mock()
    processor.preprocessor.preprocess.return_value = SimpleNamespace(audio=unit.audio, original_rms_db=-20)
    transcript = SimpleNamespace(
        text="test source speech", speaker="unknown", language="en", language_probability=1,
        start_time=speech_segment.start_time, end_time=speech_segment.end_time,
        duration_seconds=1, word_count=3,
    )
    processor._asr_processor = Mock()
    processor._asr_processor.transcribe_merged_segment.return_value = transcript
    processor._conversation_grouper = ConversationGrouper(test_config)
    processor._cache_conversation_audio = Mock()
    processor._sqlite_store = Mock()
    events = []

    def commit(*args, **kwargs):
        events.append("commit")
        if commit_fails:
            raise RuntimeError("simulated database failure")
        return 1

    processor._sqlite_store.insert_conversation.side_effect = commit
    processor.staging_queue.mark_processed.side_effect = lambda _: events.append("ack")
    result = processor.run_batch()
    assert events == (["commit"] if commit_fails else ["commit", "ack"])
    assert result["errors"] == int(commit_fails)


def test_battery_guard_does_not_load_models(test_config, monkeypatch):
    import processing.batch_processor as batch

    monkeypatch.setattr(batch.psutil, "sensors_battery", lambda: SimpleNamespace(power_plugged=False))
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.config = test_config
    processor.storage_guard = None
    processor._init_heavy_components = Mock()
    assert processor.run_batch()["paused_reason"] == "on_battery"
    processor._init_heavy_components.assert_not_called()


def test_ac_and_no_battery_allow_processing(monkeypatch):
    import processing.batch_processor as batch

    for battery in (None, SimpleNamespace(power_plugged=True)):
        monkeypatch.setattr(batch.psutil, "sensors_battery", lambda: battery)
        assert batch.processing_on_ac()
