# Voice Journal - Local, Always-On Voice Journal for Obsidian

A fully local background daemon that continuously listens through your microphone, detects speech, transcribes it, identifies speakers, classifies conversations, and writes structured notes to an Obsidian vault.

**Key Features:**
- **100% local** - No cloud APIs, no external network calls
- **Hindi + English code-switching** support
- **Speaker identification** for Shreyansh and Shivangi
- **Automatic conversation detection** and grouping
- **LLM-powered classification** (good/neutral/tense quality)
- **Structured Obsidian notes** with frontmatter
- **SQLite FTS5 search index** for fast querying

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
- **RAM**: 8GB minimum
- **Storage**: ~5GB for models
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

# Alternative: phi3:mini (faster, less accurate)
# ollama pull phi3:mini
```

### 3. Clone and Setup Python Environment

```bash
# Clone the repository
cd ~/Documents
git clone <repo-url> voice_journal
cd voice_journal

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

### Speaker Identification
```yaml
speaker:
  calibration_file: "./config/voice_profiles.json"
```

### ASR (Transcription)
```yaml
asr:
  model_size: "small"      # Options: tiny, base, small, medium
  compute_type: "int8"     # CPU-optimized quantization
  language: null           # Auto-detect (Hindi + English)
```

### Conversation Grouping
```yaml
conversation:
  gap_seconds: 90          # Group segments within this gap
  unknown_voice_ratio_threshold: 0.7  # Media detection threshold
```

### LLM Classification
```yaml
llm:
  model: "llama3.2:3b"    # Change to "phi3:mini" for faster processing
  timeout_seconds: 30
```

---

## Calibration

Voice profiles must be calibrated before first use.

### Quick Start (Using Existing Voice Memos)

```bash
# Run with auto-detected calibration files
python calibrate.py --interactive
```

### Manual Calibration

1. Record 30-60 seconds of your voice (Shreyansh)
2. Record 30-60 seconds of Shivangi's voice
3. Run calibration:

```bash
python calibrate.py \
    --shreyansh /path/to/your_voice.m4a \
    --shivangi /path/to/her_voice.m4a \
    --output config/voice_profiles.json
```

### Calibration Output

The script extracts:
- **Pitch (F0)**: Mean and standard deviation in Hz
- **Spectral Centroid**: Brightness measure in Hz
- **MFCCs**: Mel-frequency cepstral coefficients

A threshold of ±2 standard deviations is used for matching.

---

## Usage

### Start the Daemon

```bash
# Activate virtual environment
source venv/bin/activate

# Start daemon
python -m voice_journal.daemon

# Or with custom config
python -m voice_journal.daemon --config config/my_config.yaml
```

### Mute Control

```bash
# Mute
python -m voice_journal.utils.mute mute

# Unmute
python -m voice_journal.utils.mute unmute

# Toggle
python -m voice_journal.utils.mute toggle

# Check status
python -m voice_journal.utils.mute status
```

### Test Pipeline Stages

```bash
# Test full pipeline on audio file
python test_pipeline.py audio_file.m4a

# Test specific stage
python test_pipeline.py --stage vad audio_file.m4a
python test_pipeline.py --stage asr audio_file.m4a
```

### Query the Database

```bash
# Python REPL
python -c "
from voice_journal.storage import SQLiteStore
from voice_journal.config.settings import Config

store = SQLiteStore(Config())

# Search conversations
results = store.search_conversations('shivangi')

# Get conversations by date
results = store.get_by_date('2024-01-15')

# Get tense conversations
results = store.get_by_quality('tense')

# Get stats
stats = store.get_stats(days=7)
print(stats)
"
```

---

## Architecture

### Pipeline Stages

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Stage 1    │───>│   Stage 2    │───>│   Stage 3    │
│ Audio Capture│    │     VAD      │    │ Speaker ID   │
│ sounddevice  │    │  Silero VAD  │    │ librosa F0   │
└──────────────┘    └──────────────┘    └──────────────┘
                                              │
                                              v
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Stage 7    │<───│   Stage 6    │<───│   Stage 5    │
│ Obsidian     │    │ LLM Class.   │    │ Conversation │
│ Vault Notes  │    │   Ollama     │    │  Grouping    │
└──────────────┘    └──────────────┘    └──────────────┘
       │                                        │
       v                                        v
┌──────────────┐                       ┌──────────────┐
│   Stage 8    │                       │   Stage 4    │
│   SQLite     │                       │     ASR      │
│ FTS5 Index   │                       │faster-whisper│
└──────────────┘                       └──────────────┘
```

### Data Flow

1. **Audio Capture**: Continuous mic input → ring buffer
2. **VAD**: Silero VAD detects speech segments
3. **Speaker ID**: Pitch + spectral features match profiles
4. **ASR**: faster-whisper transcribes with auto-language detection
5. **Conversation**: Group segments within 90s gap
6. **LLM**: Classify type, quality, summarize
7. **Obsidian**: Write markdown notes with frontmatter
8. **SQLite**: Store metadata + FTS5 for search

---

## Performance

### CPU Performance Expectations

**Hardware**: Intel i3 (no GPU)

| Model | Real-Time Factor* | Notes |
|-------|------------------|-------|
| faster-whisper `tiny` | 0.3-0.5x | Very fast, lower accuracy |
| faster-whisper `base` | 0.5-0.7x | Good balance |
| faster-whisper `small` (recommended) | 0.8-1.2x | Best for Hindi+English |
| faster-whisper `medium` | 1.5-2.5x | Too slow for real-time |

**Real-Time Factor**: Audio duration / Processing time
- **< 1.0**: Faster than real-time (can keep up)
- **> 1.0**: Slower than real-time (will accumulate lag)

### Recommendations

If `small` model is too slow:
1. Switch to `base` model in config
2. Reduce beam_size: 5 → 1
3. Use `phi3:mini` instead of `llama3.2:3b`

If LLM classification is slow:
```yaml
llm:
  model: "phi3:mini"  # Faster, less accurate
  timeout_seconds: 15
```

---

## Known Limitations

### 1. Third-Party Voice Detection
**Issue**: If a third person speaks, they'll be tagged as "unknown" and the conversation may be flagged as "media_or_unknown".

**Workaround**: This is a tradeoff. The system only knows Shreyansh and Shivangi's voices. Any other voice is treated as the system doesn't know who it is.

### 2. Background Media Detection
**Issue**: TV/music in background may trigger VAD and create noise transcripts.

**Mitigation**:
- Adjust VAD threshold higher (0.6-0.7)
- Adjust `unknown_voice_ratio_threshold`
- Use mute control when watching media

### 3. Accuracy
- Silent segments may be missed
- Fast speech may be cut off
- Code-switching quality varies

### 4. Privacy Note
- Audio is processed **fully locally**
- No network calls for audio/transcript content
- Model downloads only on first run (external network)

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

### "Silero VAD model not found"

```bash
# Download model
mkdir -p models
wget -O models/silero_vad.onnx \
    https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx
```

### Slow Performance

```bash
# Check CPU usage
htop

# Reduce model size
# In config/default_config.yaml:
asr:
  model_size: "base"  # Downgrade from "small"

llm:
  model: "phi3:mini"  # Faster LLM
```

### Empty Transcripts

```bash
# Test VAD first
python test_pipeline.py --stage vad audio.m4a

# Check audio quality
ffprobe audio.m4a
```

---

## Project Structure

```
voice_journal/
├── audio_capture/     # Stage 1: Mic capture
├── vad/              # Stage 2: Silero VAD
├── speaker_id/       # Stage 3: Voice profiling
├── asr/              # Stage 4: faster-whisper
├── conversation/     # Stage 5: Conversation grouping
├── llm_output/       # Stage 6: Ollama classification
├── obsidian/         # Stage 7: Markdown notes
├── storage/          # Stage 8: SQLite + FTS5
├── config/           # Configuration files
├── utils/            # Logging, mute control
├── tests/            # Unit tests
├── daemon.py         # Main orchestrator
├── calibrate.py      # Voice calibration CLI
├── test_pipeline.py  # Pipeline tester
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
- **librosa**: https://librosa.org

---

*Built with care for personal journaling.*

---

## Quick Start (Linux)

```bash
# 1. Clone repository
git clone https://github.com/yourusername/voice-journal.git
cd voice-journal

# 2. Run setup
./setup.sh

# 3. Install Ollama and pull model
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2:3b

# 4. Calibrate voice profiles
source venv/bin/activate
python calibrate.py

# 5. Start the daemon
./vj-control.sh start
```
