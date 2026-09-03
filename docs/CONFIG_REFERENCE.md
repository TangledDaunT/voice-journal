# Configuration Reference

## Complete Config Schema

### Audio (Stage 1)

```yaml
audio:
  sample_rate: 16000          # Audio sample rate (Hz)
  channels: 1                 # Mono audio
  block_size: 512             # Audio block size
  ring_buffer_seconds: 30     # Internal buffer
  keep_audio: false           # Keep audio after processing
  audio_storage_path: "./audio_clips"
```

### VAD (Stage 2)

```yaml
vad:
  model_path: "./models/silero_vad.onnx"
  threshold: 0.5              # Speech detection threshold (0-1)
  min_segment_duration: 0.5   # Discard shorter segments (seconds)
  silence_padding: 0.3        # Add padding around speech
  max_segment_duration: 30.0  # Split longer segments
```

### Segment Merging (Before ASR)

```yaml
segment_merging:
  merge_gap_seconds: 2.5      # Merge segments within this gap
  min_transcription_unit_seconds: 5.0   # Minimum unit for ASR
  max_transcription_unit_seconds: 20.0   # Maximum unit (seconds)
```

### Audio Preprocessing

```yaml
preprocessing:
  enable_denoising: true
  denoising_method: "noisereduce"  # or "rnnoise"
  gain_normalization: true
  target_db: -20.0             # Target loudness
```

### ASR (Stage 4)

```yaml
asr:
  model_size: "large-v3"      # Stock Whisper model
  compute_type: "int8"        # Quantization: int8, int16, float16, float32
  device: "cpu"
  language: null              # Auto-detect for Hindi/English
  beam_size: 5               # Decoding beam width
  vad_filter: true            # Filter silence before decode
  condition_on_previous_text: false  # Prevents hallucination cascade
  initial_prompt: "Shreyansh, Shivangi. Use only Hindi and English; do not output any other language."

  # Confidence thresholds
  no_speech_prob_threshold: 0.6
  avg_logprob_threshold: -1.0
```

### Transcript Cleanup (Stage 6.5)
```yaml
cleanup:
  enabled: true
  custom_dictionary: ["Shreyansh", "Shivangi", "Cupid", "MindBridge", "OpenClaw", "LegalLawAdvisor"]
  timeout_seconds: 45
  max_tokens: 1200
  estimated_seconds_per_conversation: 30
```

### Scheduler

```yaml
scheduler:
  cpu_idle_threshold: 30.0              # CPU % below = idle
  min_idle_duration_seconds: 60         # Must be idle this long
  idle_check_interval: 30               # Check every N seconds

  guaranteed_window_enabled: true
  guaranteed_window_start_hour: 22      # 10 PM
  guaranteed_window_end_hour: 6         # 6 AM

  daytime_batch_hours: 0.5              # 30 min audio chunks
  overnight_batch_hours: 2.0            # 2 hour audio chunks

  backlog_overflow_hours: 24.0           # Switch to fallback above this
  fallback_model: "distil-large-v3"
  fallback_compute_type: "int8"
```

### Backlog

```yaml
backlog:
  warn_on_growth: true         # Warn if backlog grows day-over-day
  max_staging_hours: 72       # Force process if older than this
```

### Conversation (Stage 5)

```yaml
conversation:
  gap_seconds: 90              # Group segments within this gap
  min_segments: 2              # Minimum for conversation
  unknown_voice_ratio_threshold: 0.7  # Media detection
  rapid_alternation_threshold: 3.0
```

### LLM (Stage 6)

```yaml
llm:
  model: "llama3.2:3b"
  ollama_host: "http://localhost:11434"
  timeout_seconds: 30
  max_retries: 1
  temperature: 0.1
  max_tokens: 500
```

### Obsidian (Stage 7)

```yaml
obsidian:
  vault_path: "./obsidian_vault"
  daily_notes_dir: "VoiceJournal/Daily"
  conversation_notes_dir: "VoiceJournal/Conversations"
```

### Database (Stage 8)

```yaml
database:
  path: "./data/voice_journal.db"
  enable_fts: true             # Full-text search
```

### Daemon

```yaml
daemon:
  log_level: "INFO"
  log_file: "./logs/voice_journal.log"
  mute_file: "./data/mute_flag"
  health_check_interval: 60
```

## Environment Variables

All config can be overridden with `VJ_` prefix:

```bash
export VJ_ASR__MODEL_SIZE="distil-large-v3"
export VJ_SCHEDULER__CPU_IDLE_THRESHOLD="40.0"
```

## Validation

```bash
python scripts/validate_config.py
```

Checks:
- All required fields present
- Values in valid ranges
- Paths accessible
- Dependencies installed
