# Voice Journal - CLAUDE.md

Local, always-on voice journaling system that transcribes conversations and logs to Obsidian.

## Quick Start

```bash
# Setup
./setup.sh

# Calibrate voice profiles (do this first!)
source venv/bin/activate
python calibrate.py

# Start daemon
./vj-control.sh start

# Check status
./vj-control.sh status

# View logs
./vj-control.sh logs

# Mute/unmute
./vj-control.sh mute
./vj-control.sh unmute
```

## Architecture

```
Audio Capture → VAD → faster-whisper ASR → Daily MP3 + Daily Transcript → Web Dashboard
```

1. **Audio Capture** - Ring buffer via sounddevice, 16kHz mono
2. **VAD** - Silero VAD detects speech segments and omits silence
3. **ASR** - faster-whisper auto-detects Hindi and English per segment
4. **Daily Journal** - Speech segments are appended to one `YYYY-MM-DD.mp3`
   and one date-indexed transcript in SQLite
5. **Web Dashboard** - Browse dates, read transcripts, and play MP3 recordings

## Key Files

```
voice_journal/
├── daemon.py              # Main orchestrator
├── calibrate.py          # Voice profile calibration
├── config/
│   ├── settings.py      # Pydantic config loader
│   └── default_config.yaml  # All tunable parameters
├── audio_capture/capture.py   # Stage 1
├── vad/silero_vad.py          # Stage 2
├── speaker_id/identification.py  # Stage 3
├── asr/transcriber.py         # Stage 4
├── conversation/grouping.py   # Stage 5
├── llm_output/classifier.py   # Stage 6
├── obsidian/output.py         # Stage 7
├── storage/database.py        # Stage 8
├── web/app.py              # Flask dashboard (port 5000)
├── notify.py               # WhatsApp daily summaries via wacli
└── utils/mute.py           # Mute toggle utility
```

## Configuration

Key settings in `config/default_config.yaml`:

```yaml
# Language support - AUTO-DETECT (Hindi + English)
asr:
  language: null  # Auto-detect each segment (null) or force "en"/"hi"

# Speaker profiles (calibrate with python calibrate.py)
speaker:
  profiles:
    shreyansh:
      pitch_mean: 120.0  # Hz (male)
    shivangi:
      pitch_mean: 200.0  # Hz (female)

# Daily journal
journal:
  timezone: "Asia/Kolkata"
  storage_path: "./data/daily_journal"
```

## Language Support

**Hindi + English code-switching is fully supported:**
- `language: null` in config enables auto-detection
- faster-whisper detects language per segment (hi/en)
- Works seamlessly for mixed Hindi-English speech

## Deployment (HP Laptop via Tailscale)

```bash
# SSH into HP laptop
ssh shreyansh@100.99.161.57

# Navigate to project
cd /home/shreyansh/voice-journal

# Check status
./vj-control.sh status

# View web dashboard
# Access at: http://100.99.161.57:5000

# Start web dashboard if not running
cd /home/shreyansh/voice-journal
source venv/bin/activate
python -m voice_journal.web.app &
```

## Testing

```bash
source venv/bin/activate
pytest tests/ -v
```

## Dependencies

- Python 3.10+
- faster-whisper (CTranslate2 backend)
- torch (for Silero VAD)
- librosa (audio features)
- flask + flask-cors (web dashboard)
- ffmpeg (MP3 encoding)

## Web Dashboard

Runs on port 5000. Access via Tailscale at `http://100.99.161.57:5000`

Features:
- Real-time transcription view
- Daily statistics
- Mute/unmute controls
- Conversation history

## WhatsApp Notifications

Daily summaries sent at 9 PM IST via cron job to +917754008079.

```bash
# Manual test
wacli send text --to 917754008079 --message "Test message"
```

## Important Notes

- **No GPU required** - Runs fully on CPU (Intel i3)
- **Fully local** - No cloud APIs, all processing on-device
- **Voice profiles** - Must calibrate before first use: `python calibrate.py`
- **Mute file** - Touch `./data/mute_flag` to mute processing
- **Log location** - `./logs/voice_journal.log`
