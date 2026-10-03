# Docker deployment

The daemon and web dashboard run as separate containers. The daemon captures
speech from the host microphone, transcribes it with faster-whisper's
Hindi/English auto-detection, and writes one MP3 plus one transcript record per
local calendar day. No Ollama or LLM service is required.

## First run

On the Linux laptop that has the microphone, mount the external disk at
`/mnt/voice-journal` (or replace `DATA_ROOT` with its actual mount path):

```bash
cp .env.example .env
sudo mkdir -p /mnt/voice-journal
mkdir -p logs models
docker compose build
docker compose up -d
```

The dashboard is available at `http://localhost:5000`. `DATA_ROOT` must point
to the mounted external disk; the application writes the database and
`daily_journal/audio/YYYY-MM-DD.mp3` files below that directory. The compose
file passes `/dev/snd` to the daemon, so the host must expose an
ALSA-compatible microphone. Ensure the Docker user can write to the disk:

```bash
sudo chown -R "$USER":"$USER" /mnt/voice-journal
```

## Start on boot

Install the repository at `/opt/voice-journal`, then enable the included
systemd unit:

```bash
sudo cp deploy/voice-journal-compose.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now voice-journal-compose.service
```

The compose services use `restart: unless-stopped`, so Docker restarts them
after a daemon or host restart. The systemd unit starts the compose project
after Docker itself starts.
