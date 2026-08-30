# Documentation Index

## Getting Started
- [README.md](../README.md) - Main documentation
- [MIGRATION.md](../MIGRATION.md) - Migrate from v1.x to v2.0
- [EXAMPLES.md](../EXAMPLES.md) - Common usage examples

## Architecture & Design
- [ACCURACY_IMPROVEMENTS.md](ACCURACY_IMPROVEMENTS.md) - Quality improvements
- [SCHEDULER_BEHAVIOR.md](SCHEDULER_BEHAVIOR.md) - How scheduler works
- [CPU_USAGE.md](CPU_USAGE.md) - CPU usage patterns

## Configuration
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Complete config schema
- [BENCHMARK_GUIDE.md](BENCHMARK_GUIDE.md) - Measuring performance
- [PERFORMANCE_EXPECTATIONS.md](PERFORMANCE_EXPECTATIONS.md) - Expected performance

## Troubleshooting
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and solutions

## Testing
- `tests/` directory contains all tests
- `pytest tests/` to run all tests
- Individual test files:
  - `test_segment_merger.py`
  - `test_audio_preprocess.py`
  - `test_backlog_tracker.py`
  - `test_batch_scheduler.py`
  - `test_config_settings.py`
  - `test_obsidian_output.py`
  - `test_status.py`
  - `test_integration.py`

## Key Concepts

### Batch Architecture
The system processes audio in batches, not real-time:
1. Audio captured continuously
2. VAD detects speech segments
3. Segments staged to disk
4. Batch jobs process when CPU idle
5. Output written to Obsidian + SQLite

### Anti-Hallucination Design
Key settings prevent Whisper hallucination:
- `vad_filter: true` - Trims silence
- `condition_on_previous_text: false` - Prevents cascade
- `min_transcription_unit_seconds: 5.0` - No short clips
- `merge_gap_seconds: 2.5` - Merge before ASR

### Confidence Gating
Uncertain segments are flagged:
- ⚠️ marker in transcript
- `needs_review: true` in frontmatter
- Never silently discarded

### Scheduler Design
Daytime vs overnight behavior:
- Daytime: Idle-gated, small chunks, back-off
- Overnight: Ungated, larger chunks, continuous

### Backlog Safety
System monitors backlog:
- Tracks total hours queued
- Warns on day-over-day growth
- Falls back to faster model when >24h

## Quick Commands

```bash
# Status
make status

# Validate
make validate

# Run tests
make test

# Manual batch
make batch

# Benchmark
make benchmark

# Start daemon
make daemon
```
