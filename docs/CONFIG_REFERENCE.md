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
  threshold: 0.6              # Speech detection threshold (0-1)
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
  min_rms_db_for_asr: -55.0    # Skip near-silent units before Whisper
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
  compression_ratio_threshold: 2.4
  no_repeat_ngram_size: 3
  repetition_penalty: 1.3

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

### Dashboard Audio Playback
```yaml
dashboard:
  audio_cache_path: "./audio_cache"
  audio_retention_days: 30
  audio_bitrate_kbps: 32
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

## Storage and authentication stabilization (2026-10-15)

Set `DATA_ROOT=/mnt/music-drive` in `.env` on the HP. Docker maps that mount to
`/data`; do not add `voice-journal` to DATA_ROOT. Do not change the live value
until the existing nested files have been backed up and a migration is planned.
Daemon and manual batch entry points validate the mount and destination paths;
the web API returns 503 while the drive is unavailable. `/api/storage` provides
the dashboard banner state. Database reads use SQLite `mode=ro`, without schema
creation. `/health` and `/api/health` remain unauthenticated; other routes require
HTTP Basic Auth. Set `WEB_AUTH_USERNAME` and `WEB_AUTH_PASSWORD`; no default
password is supplied. Recreate containers after changing these variables.

`dashboard.audio_retention_days: 0` now means never automatically delete cached
audio, and is the default. Positive values explicitly enable age-based deletion.
ASR initial prompts should contain vocabulary only, not decoding instructions.
These settings are loaded at startup; runtime settings management is unfinished.
The storage removal tests are simulations, not evidence of physical hot-unplug
safety; see AUDIT.md for the remaining limitations.

## Groq-first live clips (2026-10-15)

The later Groq-first release supersedes the CPU-routing request: `GROQ_API_KEY`
comes only from the protected server environment. `transcription` configuration
controls `groq_model` (whisper-large-v3), `capture_chunk_seconds` (6),
`daily_requests` (2000), `daily_seconds` (28800), `hourly_seconds` (7200),
`requests_per_minute` (20), and `budget_fraction` (0.9). YAML changes require a
container rebuild/recreation in the current immutable-image deployment. Theme
preferences apply immediately in the browser. Groq runs on battery; local fallback
waits for AC. See DEPLOYMENT_STATUS.md for rate accounting, data control endpoints,
and exact limitations. No API route returns the key.


## Enrolled speakers (2026-10-15)

`speaker.enrolled_only` defaults to true. `similarity_threshold` defaults to 0.80,
`similarity_margin` to 0.08 and `min_matched_seconds` to 1.6. Unknown/ambiguous
speech is excluded before both ASR paths; absent/unavailable enrollment blocks
transcription. These YAML settings require restart/recreation. Profile enrollment,
recalibration and enable/disable apply immediately through `/calibration`.
No extra environment variables or cloud provider keys are needed. Embeddings
stay in the project SQLite database. Raw calibration audio is deleted after
analysis. See DEPLOYMENT_STATUS.md for retention, exports and limitations.

### Pinned input and conversation capture

`audio.input_device` is an exact PortAudio device name, resolved again on stream
start; absent or ambiguous configured names fail closed. Optional
`audio.input_card` and `audio.input_jack_control` identify an ALSA CARD jack
control, checked outside the callback. The HP deployment pins `vj_external`,
`PCH`, `Mic Jack` in its release YAML and mounts its named plug PCM configuration.
See `docs/CONTINUOUS_CAPTURE.md` for the 12 s target, 24 s maximum, verified
500 ms boundary context, 12 s conversation gap and 30 minute conversation cap.
