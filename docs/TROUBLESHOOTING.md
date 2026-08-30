# Troubleshooting Guide

## Common Issues

### 1. "Backlog growing" warning

**Symptom**: status.py shows backlog growing day-over-day

**Diagnosis**: Processing can't keep up with daily speech volume

**Solutions**:
```bash
# Check actual RTF
python benchmark_asr.py sample_audio.m4a

# If RTF > 2.0, system needs overnight + daytime
# Adjust batch sizes if needed

# Run batch manually to catch up
python -m processing.batch_processor --fallback
```

### 2. Many low-confidence segments flagged

**Symptom**: Lots of ⚠️ markers in Obsidian notes

**Diagnosis**: Audio quality is poor

**Solutions**:
- Check microphone quality
- Reduce background noise
- Ensure preprocessing enabled:
```yaml
preprocessing:
  enable_denoising: true
  gain_normalization: true
```

### 3. Speaker misidentification

**Symptom**: Wrong speaker tags

**Diagnosis**: Embeddings not calibrated properly

**Solutions**:
```bash
# Recalibrate with longer samples (60+ seconds)
python -m speaker_id.embedding_speaker_id \
    --shreyansh clean_voice_sample.m4a \
    --shivangi clean_voice_sample.m4a \
    --output config/voice_profiles.json
```

### 4. System not batching

**Symptom**: status.py shows scheduler_running but no progress

**Diagnosis**: Idle threshold not being met

**Check**:
```bash
# Check CPU usage
python -c "import psutil; print(psutil.cpu_percent(interval=5))"

# If above threshold, lower it:
# config/default_config.yaml
# scheduler.cpu_idle_threshold: 40.0
```

### 5. OOM (Out of Memory) errors

**Symptom**: Process killed during batch

**Solutions**:
- Use int8 compute type (already default)
- Reduce overnight_batch_hours
- Ensure no other memory-heavy processes running overnight

### 6. Models not found

**Symptom**: "faster-whisper model not found"

**Solutions**:
```bash
# First run downloads automatically
# Or manually:
python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3')"
```

### 7. Empty transcripts

**Symptom**: Transcription returns empty

**Diagnosis**: VAD segments too short after merging

**Solutions**:
- Lower min_transcription_unit_seconds in config
- Check audio quality with test_pipeline.py

### 8. Language always detected as 'ru'

**Symptom**: Hindi detected as Russian

**Solutions**: Already fixed in transcriber_batch.py with language correction. Update to latest.

## Diagnostic Commands

```bash
# System validation
python scripts/validate_config.py

# Status check
python status.py --format json

# Test specific audio file
python test_pipeline.py audio.m4a

# Check RTF
python benchmark_asr.py audio.m4a

# Run tests
pytest tests/ -v
```

## Log Analysis

```bash
# Check recent logs
tail -100 logs/voice_journal.log

# Search for errors
grep "ERROR" logs/voice_journal.log

# Monitor in real-time
tail -f logs/voice_journal.log
```
