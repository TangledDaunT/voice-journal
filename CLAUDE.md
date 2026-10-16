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

## Stabilization status (2026-10-15)

Read `docs/AUDIT.md` before deployment. DATA_ROOT must be the mounted external disk
(`/mnt/music-drive` on HP, `/data` inside Docker). Do not automatically migrate or
remove the live nested data directories. No credentials belong in source files.
Set WEB_AUTH_USERNAME and WEB_AUTH_PASSWORD through the environment. No deployment,
paid cloud request, model benchmark, or physical drive-removal test was performed
in this pass. Phases 1–6 of the requested upgrade remain unfinished. Do not claim
speaker accuracy, cloud routing, WAL mode, or the Hermes schema are implemented.

## Active release update (2026-10-15)

The later user instruction is Groq-first (including on battery), local-only fallback
on cloud failures; the active daemon uses `processing/live_pipeline.py` rather than
BatchScheduler. Read the latest section of `docs/DEPLOYMENT_STATUS.md`. Active HP
release: `/home/shreyansh/voice-journal-groq-20261015`, Compose project
`voice-journal-stabilized`. Preserve protected server `.env` files and never expose
GROQ_API_KEY. Never execute clear-all against live data as a test. The browser's
confirmation phrase authorizes an explicit user-requested deletion. Temporary tests
cover clear, import, export, FTS, mute, journal detail, quotas and fallback.


## Enrolled-speaker release (2026-10-15)

Latest HP source: `/home/shreyansh/voice-journal-speakers-20261015`, image
`voice-journal:enrolled-voices-20261015`, same Compose project. A local Resemblyzer
gate now precedes both ASR paths. Enroll real people using `/calibration` (30s
on the HP microphone); never create invented production profiles. Zero profiles
means no transcription uploads. Profiles update immediately; matching remains
probabilistic, with replay/overlap limitations. See latest DEPLOYMENT_STATUS.md
for validation and data retention. Preserve the current mute preference.

## Continuous-conversation release (2026-10-16)

Active HP source: `/home/shreyansh/voice-journal-continuous-20261016`, image
`voice-journal:continuous-20261016`, same Compose project. Read the latest
DEPLOYMENT_STATUS.md and CONTINUOUS_CAPTURE.md. Keep the named PCH external-mic
PCM/jack guard and shared IPC namespace. Dashboard listening uses expiring shared
RAM and does not change normal journal mute or bypass the speaker gate. Preserve
chunk core/context metadata and both raw language-policy responses.

## Capture stall recovery (2026-10-16)

Active HP release is now `/home/shreyansh/voice-journal-recovery-20261016`, image
`voice-journal:capture-recovery-20261016`. Both real profiles are enabled. Preserve
`audio/recovery/capture-stall-20261016` and its manifest; it is a backup of the
memory queue, not a second import queue. See the latest deployment-status section.

## Audio continuity repair (2026-10-16)

Active HP release: `/home/shreyansh/voice-journal-audiofix-20261016`, image
`voice-journal:audio-continuity-20261016`. Read `docs/AUDIO_CONTINUITY_AUDIT.md` and
latest deployment status. Preserve separate capture/media/processing locks and
clear-all lock ordering; do not hold capture staging behind ASR. Staging is FLAC
with WAV fallback, older Opus remains supported. ADC time determines recording
timestamps. No ASR text prompt; flag historical prompt echoes without rewriting
source payloads. Full recording playback includes retained unverified room audio;
transcription still uses verified spans only. Preserve both enabled real profiles.

## Microphone studio and storage recovery (2026-10-16)

Active release is `/home/shreyansh/voice-journal-studio-20261016`, daemon image
`voice-journal:microphone-studio-20261016`, web image
`voice-journal:microphone-studio-ui-20261016`. Public dashboard is
https://voice.tangleddaunt.dpdns.org through existing Cloudflare/Nginx. Read
`docs/MICROPHONE_STUDIO.md`. Preserve external nginx-proxy-net membership and dynamic
Docker DNS; avoid the old 10 req/s limit for live microphone polling.

A drive reconnect changed sdb1 to sdc1; always use UUID 6EFF-790D. Recovery timer
voice-journal-recover.timer uses /etc/voice-journal-release. Set
/run/voice-journal-maintenance during maintenance and remove it afterward.
Sound settings affect monitors/new enhanced files; original ASR/gate signal stays
untouched. Mac monitoring stays local; OS/browser permission is required. Keep
cancel/timeout and late-stream cleanup for pending native microphone requests.
