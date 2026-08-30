# Changelog

## [2.0.0] - 2025-08-31 - Batch Architecture Refactor

### Breaking Changes

- Daemon entry point changed: Use `python daemon_v2.py` instead of `python -m voice_journal.daemon`
- Speaker calibration now uses embeddings instead of pitch thresholds
- Configuration format updated with new sections
- Database schema has new tables for backlog tracking

### Added

#### Fix 0: Benchmarking
- `benchmark_asr.py`: Measure RTF on target hardware
- Reports actual processing time for daily speech volume

#### Fix 1: Batch Architecture
- `daemon_v2.py`: New batch-mode daemon
- `processing/`: New module for batch processing
- Staging queue for VAD segments
- `StagingQueue`: Manages segment lifecycle

#### Fix 2: Segment Merging
- `vad/segment_merger.py`: Merge segments before ASR
- 2.5s gap threshold for merging
- 5s minimum transcription unit
- Prevents hallucination on short clips

#### Fix 3: Large-v3 Model
- Default model changed to `large-v3`
- Anti-hallucination settings enabled
- `vad_filter=true`
- `condition_on_previous_text=false`
- `beam_size=5`

#### Fix 4: Confidence Gating
- `asr/transcriber_batch.py`: Batch ASR with confidence
- Captures `no_speech_prob` and `avg_logprob`
- Flags uncertain segments with ⚠️
- `needs_review` frontmatter for notes

#### Fix 5: Audio Preprocessing
- `audio_capture/preprocess.py`: Denoising + normalization
- Uses noisereduce library
- -20dB target loudness

#### Fix 6: Embedding Speaker ID
- `speaker_id/embedding_speaker_id.py`: Robust embeddings
- Resemblyzer for speaker embeddings
- Cosine similarity matching
- Replaced pitch-threshold method

#### Fix 7: Documentation
- Completely rewrote README
- `MIGRATION.md`: Migration guide
- `docs/ACCURACY_IMPROVEMENTS.md`: Quality explainer
- `docs/BENCHMARK_GUIDE.md`: Benchmark usage
- `docs/SCHEDULER_BEHAVIOR.md`: Scheduler reference

#### Fix 8: Scheduler + Backlog
- `processing/batch_processor.py`: BatchProcessor + BatchScheduler
- `storage/database.py`: BacklogTracker
- `status.py`: CLI status checker
- CPU idle detection via psutil
- Guaranteed overnight window (10 PM - 6 AM)
- Daytime: 0.5h chunks (backs off if user returns)
- Overnight: 2h chunks (full-CPU acceptable)
- Adaptive fallback when backlog > 24h

### Changed

- `config/default_config.yaml`: Updated for batch mode
- `config/settings.py`: New config models
- `requirements.txt`: Added dependencies
- `obsidian/output.py`: Confidence markers in output

### Fixed

- Hallucination on short/silent segments (merge before ASR)
- Fragile speaker ID (embeddings instead of pitch)
- Silent acceptance of uncertain transcripts (confidence gating)
- Real-time constraint preventing accuracy (batch mode)

---

## [1.0.0] - 2024-XX-XX - Initial Release

- Real-time voice journal pipeline
- Silero VAD for speech detection
- faster-whisper for transcription
- Ollama for LLM classification
- Obsidian markdown output
- SQLite FTS5 search
