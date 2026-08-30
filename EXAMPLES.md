# Voice Journal: Common Usage Examples

## Starting the System

```bash
# Basic start
python daemon_v2.py

# With custom config
python daemon_v2.py --config config/production.yaml

# Start muted
python daemon_v2.py --mute
```

## Checking System Status

```bash
# Text status
python status.py

# JSON for monitoring tools
python status.py --format json

# Quick check via script
./scripts/check_idle.sh
```

## Manual Processing

```bash
# Process backlog immediately
python -m processing.batch_processor

# Use faster fallback model
python -m processing.batch_processor --fallback

# With custom config
python -m processing.batch_processor --config config/custom.yaml
```

## Benchmarking

```bash
# Test with your own audio
python benchmark_asr.py recording.m4a

# Test with multiple files
python benchmark_asr.py file1.m4a file2.m4a file3.m4a

# JSON output
python benchmark_asr.py sample.m4a --output results.json
```

## Calibration

```bash
# Calibrate with voice samples
python -m speaker_id.embedding_speaker_id \
    --shreyansh path/to/shreyansh_voice.m4a \
    --shivangi path/to/shivangi_voice.m4a \
    --output config/voice_profiles.json
```

## Searching Conversations

```python
# Python REPL
from storage.database import SQLiteStore
from config.settings import Config

store = SQLiteStore(Config())

# Search for keyword
results = store.search_conversations('project')

# Get conversations by date
results = store.get_by_date('2025-08-31')

# Get tense conversations
results = store.get_by_quality('tense')

# Get stats
stats = store.get_stats(days=7)
```

## Mute Control

```bash
# Mute microphone
python -m utils.mute mute

# Unmute
python -m utils.mute unmute

# Check status
python -m utils.mute status
```

## Troubleshooting

### Check if backlog is growing

```bash
python status.py | grep "backlog"
```

### Validate configuration

```bash
python scripts/validate_config.py
```

### Run tests

```bash
# All tests
pytest tests/ -v

# Specific test
pytest tests/test_segment_merger.py -v
```

## Makefile Shortcuts

```bash
make status     # Check status
make batch      # Run batch
make validate   # Validate config
make test       # Run tests
```
