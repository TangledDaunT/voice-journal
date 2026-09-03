# Voice Journal - Local, Always-On Voice Journal for Obsidian

A fully local background daemon that continuously listens through your microphone, detects speech, transcribes it, identifies speakers, classifies conversations, and writes structured notes to an Obsidian vault.

**Key Features:**
- **100% local** - No cloud APIs, no external network calls
- **Hindi + English code-switching** support
- **Speaker identification** for Shreyansh and Shivangi (embedding-based)
- **Automatic conversation detection** and grouping
- **LLM-powered classification** (good/neutral/tense quality)
- **Structured Obsidian notes** with frontmatter
- **SQLite FTS5 search index** for fast querying
- **Batch processing** - Accuracy over speed, no real-time constraint

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Calibration](#calibration)
5. [Usage](#usage)
6. [Architecture](#architecture)
7. [Performance](#performance)
8. [Known Limitations](#known-limitations)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- **OS**: Ubuntu 24.04 (or similar Linux)
- **CPU**: Intel i3 or equivalent (8th gen+ recommended)
- **RAM**: 8GB minimum (16GB recommended for large-v3 model)
- **Storage**: ~8GB for models
- **GPU**: NOT required (CPU-only inference)

### Software Dependencies
- Python 3.10+
- PortAudio (for audio capture)
- Ollama (for local LLM)

---

## Installation

### 1. Install System Dependencies

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y \
    portaudio19-dev \
    python3-pip \
    python3-venv \
    ffmpeg

# PortAudio for audio capture
sudo apt install libportaudio2 libportaudiocpp0
```

### 2. Install Ollama and Pull Model

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve &

# Pull the LLM model (CPU-optimized)
ollama pull llama3.2:3b
```

### 3. Clone and Setup Python Environment

```bash
# Clone the repository
cd ~/Documents
git clone https://github.com/TangledDaunT/voice-journal.git
cd voice-journal

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download Silero VAD model
mkdir -p models
wget -O models/silero_vad.onnx \
    https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx
```

### 4. Initialize Directories

```bash
# Create required directories
mkdir -p config
mkdir -p logs
mkdir -p data
mkdir -p audio_clips/staging
mkdir -p obsidian_vault/VoiceJournal/{Daily,Conversations}
```

---

## Configuration

Configuration is stored in `config/default_config.yaml`. Key settings:

### Audio Capture
```yaml
audio:
  sample_rate: 16000
  channels: 1
  keep_audio: false  # Set to true to save audio clips
```

### VAD (Voice Activity Detection)
```yaml
vad:
  threshold: 0.5
  min_segment_duration: 0.5  # Discard short noise
  max_segment_duration: 30.0  # Split long segments
```

### Segment Merging (Fix 2)
```yaml
segment_merging:
  merge_gap_seconds: 2.5  # Merge segments separated by less than this
  min_transcription_unit_seconds: 5.0  # Don't transcribe shorter units
  max_transcription_unit_seconds: 20.0  # Bound language-misdetection damage to a short span
```

### ASR (Transcription) - Now batch-processed
```yaml
asr:
  model_size: "large-v3"  # Stock Whisper large model
  compute_type: "int8"
  language: null          # Auto-detect (Hindi + English)
  vad_filter: true        # Trim silence before transcription
  condition_on_previous_text: false  # Prevent hallucination cascade
  beam_size: 5            # Full beam for accuracy
  initial_prompt: "Shreyansh, Shivangi. Use only Hindi and English; do not output any other language."
  
  # Confidence thresholds for uncertain segments
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
```

### Batch Processing Scheduler
```yaml
scheduler:
  cpu_idle_threshold: 30.0  # Percentage
  guaranteed_window:
    start_hour: 22  # 10 PM
    end_hour: 6    # 6 AM
  backlog_overflow_hours: 24.0  # Switch to faster model if exceeded
  fallback_model: "distil-large-v3"
```

---

## Calibration

### Speaker Identification (Embedding-based)

Voice profiles must be calibrated before first use. The new system uses speaker embeddings (not pitch threshold).

```bash
# Activate virtual environment
source venv/bin/activate

# Record 30-60 seconds of your voice (Shreyansh)
# Record 30-60 seconds of Shivangi's voice

# Run calibration
python -m speaker_id.embedding_speaker_id \
    --shreyansh /path/to/your_voice.m4a \
    --shivangi /path/to/her_voice.m4a \
    --output config/voice_profiles.json
```

The calibration extracts speaker embeddings using Resemblyzer or SpeechBrain, which are more robust than the old pitch-threshold method.

---

## Usage

### Start the Daemon

```bash
# Activate virtual environment
source venv/bin/activate

# Start daemon (batch mode)
python daemon_v2.py

# Or with custom config
python daemon_v2.py --config config/my_config.yaml
```

### Check Status

```bash
# Check backlog, processing status, and health
python status.py

# JSON format
python status.py --format json
```

### Run Batch Job Manually

```bash
# Process all staged segments immediately
python -m processing.batch_processor

# Use fallback model (faster)
python -m processing.batch_processor --fallback
```

### Mute Control

```bash
# Mute
python -m utils.mute mute

# Unmute
python -m utils.mute unmute

# Check status
python -m utils.mute status
```

---

## Architecture

### Batch Processing Pipeline (New)

The system now processes audio in **batch mode** rather than real-time. This is a fundamental change from the original design.

```
┌──────────────────────────────────────────────────────────────┐
│                    REAL-TIME (LIGHTWEIGHT)                    │
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│  │   Stage 1    │───>│   Stage 2    │───>│   Staging    │    │
│  │ Audio Capture│    │     VAD      │    │   Queue      │    │
│  │ sounddevice  │    │  Silero VAD  │    │ (disk + DB)  │    │
│  └──────────────┘    └──────────────┘    └──────────────┘    │
│                                                   │            │
└──────────────────────────────────────────────────┼────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────┐
│                    BATCH PROCESSING                           │
│              (Runs when CPU is idle / overnight)             │
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│  │   Segment    │───>│ Preprocessing│───>│    ASR       │    │
│  │   Merging    │    │   Denoise    │    │ large-v3     │    │
│  │ (gap < 2.5s) │    │   Normalize  │    │ + confidence │    │
│  └──────────────┘    └──────────────┘    └──────────────┘    │
│                                                 │              │
│                                                 ▼              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│  │   Stage 7    │<───│   Stage 6    │<───│   Stage 5    │    │
│  │ Obsidian     │    │ LLM Class.   │    │ Conversation │    │
│  │ Vault Notes  │    │   Ollama     │    │  Grouping    │    │
│  └──────────────┘    └──────────────┘    └──────────────┘    │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────┐                       ┌──────────────┐      │
│  │   Stage 8    │                       │   Stage 3    │      │
│  │   SQLite     │                       │ Speaker ID   │      │
│  │ FTS5 Index   │                       │ (Embeddings) │      │
│  └──────────────┘                       └──────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

### Key Architecture Changes

1. **Segments are merged BEFORE transcription** (Fix 2)
   - Consecutive VAD segments separated by <2.5s are merged
   - Minimum 5s transcription unit prevents hallucination on short clips
   - This is critical for accuracy - Whisper hallucinates on short, isolated segments

2. **Audio preprocessing** (Fix 5)
   - Denoising applied before VAD and ASR
   - Gain normalization for consistent loudness
   - Reduces false VAD triggers and improves transcription

3. **Confidence gating** (Fix 4)
   - Every segment gets `no_speech_prob` and `avg_logprob`
   - Uncertain segments are kept but flagged with ⚠️
   - Notes with low-confidence segments get `needs_review: true` frontmatter

4. **Embedding-based speaker ID** (Fix 6)
   - Replaced fragile pitch-threshold method
   - Uses resemblyzer or speechbrain for speaker embeddings
   - Cosine similarity matching against reference embeddings

5. **Idle-triggered scheduler** (Fix 8)
   - Batch jobs run when CPU is idle (<30% usage)
   - Guaranteed overnight window (10 PM - 6 AM)
   - Adaptive fallback to distil-large-v3 when backlog overflows

### Data Flow

1. **Audio Capture**: Continuous mic input → ring buffer
2. **VAD**: Silero VAD detects speech segments
3. **Staging**: Segments saved to disk, tracked in SQLite
4. **Batch Job** (when scheduled):
   - Merge segments (gap-based)
   - Preprocess (denoise, normalize)
   - Transcribe (large-v3 with anti-hallucination settings)
   - Identify speakers (embeddings)
   - Group into conversations (90s gap)
   - Classify (LLM)
   - Write to Obsidian + SQLite

---

## Performance

### Batch Processing Performance

**Hardware**: Intel i3 (no GPU)

| Model | Real-Time Factor* | Quality | Notes |
|-------|------------------|---------|-------|
| faster-whisper `large-v3` | ~2.0-2.5x | Best | Accuracy over speed |
| faster-whisper `distil-large-v3` | ~1.0-1.2x | Good | Fallback for overflow |

**Real-Time Factor**: Processing time ÷ Audio duration
- **< 1.0**: Faster than real-time
- **~2.0**: Large-v3 on i3 (typical)
- **Higher RTF = More accurate transcription**

### Expected Daily Processing Time

With **3-6 hours of actual speech per day**:

- **large-v3 (RTF ~2.0)**: 6-12 hours of processing time per day
- **With overnight window (10 PM - 6 AM)**: 8 hours available
- **If backlog grows**: Automatically switches to fallback model

Run the benchmark on your hardware:
```bash
python benchmark_asr.py path/to/sample_audio.m4a
```

---

## Known Limitations

### 1. Hallucination on Short/Silent Segments (FIXED)

**Previous Issue**: Whisper would hallucinate (invent text) on short, isolated, or near-silent segments. This is a known failure mode of chunked Whisper pipelines.

**Mitigations**:
- Segments are now merged BEFORE transcription (minimum 5s units)
- `vad_filter=true` trims silence before decoding
- `condition_on_previous_text=false` prevents hallucination cascades
- Uncertain segments are flagged with ⚠️ markers
- Audio preprocessing (denoising) reduces silence/noise issues

### 2. Third-Party Voice Detection

**Issue**: If a third person speaks, they'll be tagged as "unknown".

**Workaround**: This is a tradeoff. The system only knows registered voice profiles. Any other voice is treated as unknown.

### 3. Background Media Detection

**Issue**: TV/music in background may trigger VAD.

**Mitigations**:
- Adjust VAD threshold higher (0.6-0.7)
- Speaker ID helps filter unknown voices
- Use mute control when watching media

### 4. Code-Switching Accuracy

**Issue**: Stock Whisper can commit to one language for a mixed Hindi-English chunk, producing garbled words in the other language.

**Mitigation**: The default `large-v3` model is explicitly prompted to output only Hindi and English. A separate Stage 6.5 cleanup pass improves readability without replacing raw ASR. Use `compare_asr_models.py` to manually compare future ASR model swaps before changing the default.

### 5. Transcript Cleanup

The optional Stage 6.5 Ollama pass removes meaningless fillers, resolves clear self-corrections, fixes obvious dictionary terms, and adds punctuation. It is conservative and never replaces the raw transcript: conversation notes and SQLite retain both `raw_transcript` and `cleaned_transcript`. Cleanup failures fall back to raw text and do not block processing. The extra Ollama call adds processing time per conversation and is included in the batch job duration/backlog estimate.

### 6. Backlog Growth

**Issue**: If daily speech exceeds overnight processing capacity, backlog grows.

**Mitigations**:
- `status.py` shows backlog depth and warns on growth
- Adaptive fallback to faster model when backlog >24h
- Run batch jobs manually if needed

---

## Troubleshooting

### "Ollama model not available"

```bash
# Check Ollama is running
ollama list

# Pull model if missing
ollama pull llama3.2:3b

# Start Ollama service
ollama serve
```

### "Audio device not found"

```bash
# List audio devices
python -c "import sounddevice as sd; print(sd.query_devices())"

# Check permissions
sudo usermod -a -G audio $USER
```

### "Backlog growing" warning

```bash
# Check current status
python status.py

# Run batch job manually
python -m processing.batch_processor

# Use fallback model if behind
python -m processing.batch_processor --fallback
```

### "resemblyzer not found"

```bash
# Install speaker embedding library
pip install resemblyzer

# Or use heavier alternative
pip install speechbrain
```

### Low-confidence segments flagged

This is expected behavior. The system is being honest about uncertainty:

- Review flagged segments in Obsidian (marked with ⚠️)
- Check if audio quality can be improved
- Consider re-processing with cleaner audio

---

## Project Structure

```
voice_journal/
├── audio_capture/     # Stage 1: Mic capture + preprocessing
├── vad/              # Stage 2: Silero VAD + segment merging
├── speaker_id/       # Stage 3: Embedding-based speaker ID
├── asr/              # Stage 4: faster-whisper (batch mode)
├── conversation/     # Stage 5: Conversation grouping
├── llm_output/       # Stage 6: Ollama classification
├── obsidian/         # Stage 7: Markdown notes
├── storage/          # Stage 8: SQLite + FTS5 + backlog tracking
├── processing/       # Batch processor + scheduler
├── config/           # Configuration files
├── utils/            # Logging, mute control
├── tests/            # Unit tests
├── daemon_v2.py      # Main daemon (batch mode)
├── benchmark_asr.py  # Model benchmarking script
├── status.py         # CLI status checker
├── calibrate.py      # Voice calibration CLI
└── README.md         # This file
```

---

## Contributing

This is a personal project, but contributions are welcome:

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

---

## License

MIT License - Use freely for personal projects.

---

## Acknowledgments

- **Silero VAD**: https://github.com/snakers4/silero-vad
- **faster-whisper**: https://github.com/guillaumekln/faster-whisper
- **Ollama**: https://ollama.ai
- **Resemblyzer**: https://github.com/resemble-ai/Resemblyzer

---

*Built with care for personal journaling. Accuracy over speed.*
