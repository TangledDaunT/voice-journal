# Quick Reference Card

## Start System
```bash
python daemon_v2.py
```

## Check Status
```bash
python status.py
```

## Process Backlog Now
```bash
python -m processing.batch_processor
```

## Calibrate Speakers
```bash
python -m speaker_id.embedding_speaker_id \
    --shreyansh voice.m4a \
    --shivangi voice.m4a
```

## Benchmark RTF
```bash
python benchmark_asr.py audio.m4a
```

## Validate Config
```bash
python scripts/validate_config.py
```

## Run Tests
```bash
pytest tests/ -v
```

## Key Files
```
daemon_v2.py          - Main daemon
status.py             - Status checker
config/default_config.yaml - Configuration
docs/INDEX.md         - Documentation index
```

## Important Paths
```
audio_clips/staging/  - Queued segments
obsidian_vault/       - Output notes
data/voice_journal.db - SQLite database
logs/                 - Log files
```

## Emergency Commands

### Stop daemon
```bash
pkill -f daemon_v2.py
```

### Clear backlog
```bash
./scripts/reset_backlog.sh
```

### Health check
```bash
./scripts/health_check.sh
```
