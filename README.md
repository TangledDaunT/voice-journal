# Voice Journal - Dockerized Day-wise Audio Archive & Transcript System

A simplified, Dockerized voice journal system that captures audio, performs VAD, stores segments on an external drive, and provides batch transcription with a web dashboard for playback and search.

## Key Features

- **Audio Capture**: Continuous microphone input with Silero VAD for speech detection
- **Day-wise Organization**: All data organized by local date (Asia/Kolkata)
- **External Drive Storage**: Automatically detects and uses 1TB external drive for all storage
- **Batch Processing**: Efficient transcription using faster-whisper with optional speaker gender tagging
- **Web Dashboard**: Flask-based interface for browsing, playing, and searching recordings
- **Dockerized**: Easy deployment with docker-compose, separated daemon and web services
- **Migration Script**: One-time migration tool to move existing data to new structure

## Storage Structure

All data is stored under `DATA_ROOT/voice-journal/`:
```
audio/YYYY-MM-DD/segments/HHMMSS.opus   (VAD speech segments)
audio/YYYY-MM-DD/full_day.opus          (concatenated day recording)
transcripts/YYYY-MM-DD/segments.jsonl   (per-segment: start_time, end_time, text, language, confidence, audio_path)
transcripts/YYYY-MM-DD/full_day.txt     (entire day transcript with [HH:MM:SS] timestamps)
db/voice_journal.db                     (SQLite database in WAL mode)
```

## Prerequisites

- Ubuntu 22.04+ or compatible Linux distribution
- 1TB+ external drive (formatted as ext4 or compatible)
- Docker and Docker Compose
- Microphone input device
- Approximately 2GB RAM, 2 CPU cores reserved for operation

## Installation

### 1. Connect External Drive
Connect your 1TB external drive to the system. The system will auto-detect it or you can manually specify the path.

### 2. Clone Repository
```bash
git clone https://github.com/TangledDaunT/voice-journal.git
cd voice-journal
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env to set DATA_ROOT if not auto-detected, adjust resource limits, etc.
```

### 4. Build and Start Services
```bash
./vj-control.sh start
```

## Configuration

### Environment Variables (.env)

Key variables:
- `DATA_ROOT`: Root directory for all data (auto-detected if empty)
- Resource limits for each service (DAEMON_CPUS, WEB_CPUS, TRANSCRIBE_CPUS, etc.)
- Audio processing parameters (sample rates, VAD thresholds, ASR settings)
- Batch processing scheduler configuration
- Web dashboard authentication token

### Docker Resource Limits

Resource usage can be controlled via `.env`:
- Daemon: CPU and memory limits for capture/VAD/staging
- Web: CPU and memory limits for dashboard
- Transcribe: CPU and memory limits for batch transcription jobs

## Usage

### Starting Services
```bash
./vj-control.sh start
```

### Stopping Services
```bash
./vj-control.sh stop
```

### Checking Status
```bash
./vj-control.sh status
```

### Viewing Logs
```bash
./vj-control.sh logs
```

### Muting/Unmuting Microphone
```bash
./vj-control.sh mute
./vj-control.sh unmute
./vj-control.sh toggle
```

### Manual Transcription
```bash
# Transcribe specific date
./vj-control.sh transcribe-date 2026-10-03

# Or using docker compose directly
docker compose run --rm transcribe --date 2026-10-03
```

### Accessing Web Dashboard
Open browser to: `http://localhost:5000` (or via Tailscale)

Features:
- Browse recordings by date
- Play full-day recordings with seek and speed controls
- View transcripts with timestamps
- Click transcript lines to seek to that moment in audio
- Download audio and transcript files
- Low-confidence segments flagged for review

## Data Organization

### Audio Files
- Raw VAD segments stored as Opus files: `audio/YYYY-MM-DD/segments/HHMMSS.opus`
- Daily concatenated recordings: `audio/YYYY-MM-DD/full_day.opus`
- Format: Opus, mono, 16kHz for efficient storage

### Transcripts
- Per-segment JSONL: `transcripts/YYYY-MM-DD/segments.jsonl`
- Full day text: `transcripts/YYYY-MM-DD/full_day.txt`
- Format: JSONL with metadata, plain text with [HH:MM:SS] timestamps

### Database
- SQLite database: `db/voice_journal.db`
- Contains: segment metadata, transcript index, conversation groupings
- WAL mode for better concurrent access

## Architecture

### Services
1. **Daemon Service**: 
   - Audio capture from microphone
   - Silero VAD for speech detection
   - Segment staging to disk (Opus + JSON metadata)
   - Backlog tracking in SQLite

2. **Web Service**:
   - Flask dashboard for playback and browsing
   - Audio streaming with HTTP Range support
   - Transcript display with interactive seeking

3. **Transcribe Service** (on-demand):
   - Batch transcription using faster-whisper
   - Segment merging and preprocessing
   - Speaker identification (optional)
   - Full-day transcript and audio assembly

### Processing Flow
1. Audio captured → VAD detects speech segments
2. Segments saved as Opus files with metadata JSON
3. Backlog tracker monitors staged segments
4. Scheduler triggers batch transcription when:
   - CPU is idle (<30%) for 60+ seconds, OR
   - In guaranteed window (10PM-6AM daily), OR
   - Manual transcription requested
5. Batch processor loads segments, merges, preprocesses, transcribes
6. Results stored in SQLite, full-day files generated
7. Dashboard serves files for playback and browsing

## Migration

To migrate existing data from previous voice-journal installations:

```bash
# Dry run first to see what would be migrated
python3 migrate_data.py --dry-run

# Actual migration
python3 migrate_data.py
```

The script will:
1. Auto-detect external drive for DATA_ROOT
2. Create new directory structure
3. Migrate existing database
4. Migrate audio files to date-based structure
5. Migrate transcript files to date-based structure
6. Leave original files intact (manual cleanup after verification)

## Maintenance

### Log Rotation
Docker containers use json-file log drivers with automatic rotation:
- Max size: 10m per file
- Max files: 3

### Updates
```bash
# Pull latest changes
git pull

# Rebuild and restart
./vj-control.sh restart
```

### Backup
Backup the entire `DATA_ROOT/voice-journal/` directory to preserve all recordings, transcripts, and database.

## Troubleshooting

### No Audio Detection
1. Check microphone permissions: `ls -l /dev/snd/*`
2. Verify audio group membership in Docker
3. Check daemon logs: `./vj-control.sh logs`

### External Drive Not Detected
1. Ensure drive is mounted and writable
2. Manually set DATA_ROOT in .env file
3. Check system logs for mount points

### Web Dashboard Not Accessible
1. Check service status: `./vj-control.sh status`
2. Verify port 5000 is free
3. Check web service logs

### Transcription Backlog
1. Check scheduler status in dashboard or logs
2. Verify CPU usage allows processing
3. Check guaranteed window schedule (10PM-6AM)

## Performance Notes

- Designed for continuous operation on modest hardware (i3 CPU, no GPU)
- Idle CPU usage typically <5% when not processing
- Memory usage: ~500MB-1GB depending on workload
- Storage efficient: Opus audio at ~12kbps ≈ 0.6MB/hour of speech
- Batch processing runs during idle periods or overnight window

## Customization

### Speaker Identification
Speaker gender tagging is available but disabled by default to save resources. Enable in config if needed.

### Whisper Models
Change `ASR_MODEL_SIZE` in .env to use different faster-whisper models (tiny, base, small, medium, large-v2, large-v3).

### Language Processing
The system is optimized for Hindi/English code-switching. Adjust `ASR_LANGUAGE` and `ASR_INITIAL_PROMPT` as needed.

## License

MIT License - see LICENSE file for details
