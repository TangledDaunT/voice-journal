# Migration Guide: Real-time to Batch Processing

This guide helps you migrate from the old real-time pipeline to the new batch processing architecture.

## Why This Change?

The old real-time pipeline had a fundamental design flaw that caused unusable transcripts:
- VAD segments as short as 0.5 seconds were sent directly to Whisper
- Short, isolated segments cause Whisper to hallucinate (invent text instead of admitting silence)
- Real-time factor constraint forced small models and low beam sizes, sacrificing accuracy

The new batch architecture:
- Merges segments before transcription (minimum 5s units)
- Uses large-v3 model with proper anti-hallucination settings
- Processes when CPU is idle, not in real-time
- Flags uncertain segments transparently

## Breaking Changes

### 1. Daemon Entry Point

**Old:**
```bash
python -m voice_journal.daemon
```

**New:**
```bash
python daemon_v2.py
```

### 2. Speaker Calibration Required

The old pitch-threshold calibration is no longer used. You must recalibrate with embeddings:

```bash
python -m speaker_id.embedding_speaker_id \
    --shreyansh /path/to/shreyansh_voice.m4a \
    --shivangi /path/to/shivangi_voice.m4a \
    --output config/voice_profiles.json
```

### 3. Status Command

New command to check system health:
```bash
python status.py
```

### 4. Config Changes

Update your `config/default_config.yaml`:

Key changes:
- `asr.model_size`: Now defaults to `large-v3` (was `small`)
- `asr.condition_on_previous_text`: Now `false` (was unset)
- New `segment_merging` section for merge-before-transcribe
- New `scheduler` section for batch processing
- New `preprocessing` section for audio denoising

### 5. Database Schema additions

New tables for backlog tracking:
- `backlog_tracking`: Per-segment metadata
- `backlog_summary`: Aggregate metrics

These are created automatically on first run.

## Migration Steps

### Step 1: Backup Existing Data

```bash
cp -r data data_backup
cp -r obsidian_vault obsidian_vault_backup
cp config/default_config.yaml config_backup.yaml
```

### Step 2: Pull Changes

```bash
git pull
pip install -r requirements.txt
```

### Step 3: Recalibrate Speaker Profiles

```bash
# You need 30-60 seconds of clean audio for each speaker
python -m speaker_id.embedding_speaker_id \
    --shreyansh path/to/shreyansh_voice.m4a \
    --shivangi path/to/shivangi_voice.m4a \
    --output config/voice_profiles.json
```

### Step 4: Update systemd Service (if applicable)

Edit your systemd service file to use the new daemon:

```bash
sudo nano /etc/systemd/system/voice-journal.service
```

Change:
```
ExecStart=/path/to/venv/bin/python -m voice_journal.daemon
```

To:
```
ExecStart=/path/to/venv/bin/python /path/to/voice-journal/daemon_v2.py
```

Reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart voice-journal
```

### Step 5: Verify

Check status:
```bash
python status.py
```

You should see:
- `scheduler_running: True`
- `backlog_hours: 0.0` (initially)
- Your config summary

## Model Downloads

The first run will download `large-v3` model (~3GB). Ensure:
- Disk space available (~8GB total for all models)
- Internet connection for initial download
- Subsequent runs are fully offline

## Monitoring

### Check Backlog

```bash
# Text format
python status.py

# JSON for monitoring
python status.py --format json
```

### Manual Batch Processing

If backlog is growing:

```bash
# Normal processing
python -m processing.batch_processor

# With fallback model (faster)
python -m processing.batch_processor --fallback
```

## Tuning

### Adjust Batch Sizes

In `config/default_config.yaml`:

```yaml
scheduler:
  daytime_batch_hours: 0.5  # Smaller = more responsive to user return
  overnight_batch_hours: 2.0  # Larger = more progress overnight
```

### Adjust Idle Thresholds

```yaml
scheduler:
  cpu_idle_threshold: 30.0  # Lower = more conservative
  min_idle_duration_seconds: 60  # Longer = ensure true idle
```

## Troubleshooting

### "Backlog growing" warning

This means processing can't keep up:
1. Check RTF with `python benchmark_asr.py audio.m4a`
2. If RTF is high, system may need overnight window + daytime chunks
3. Fallback model will activate automatically at 24h backlog

### transcripts seem muted/wrong

The new confidence system flags uncertain segments:
- Check for `⚠️` markers in Obsidian notes
- If many segments flagged, check microphone quality
- Audio preprocessing helps (denoising enabled by default)

### Speaker misidentified

Embeddings are more robust but need good calibration:
- Use 60+ seconds of clean audio
- Avoid background noise in calibration samples
- Recalibrate if detection is poor
