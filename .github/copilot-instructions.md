# Voice Journal Project Guidelines

## Build, Test, and Lint

Use Python 3.10+ and a virtual environment. The normal setup is:

```bash
./setup.sh
source venv/bin/activate
```

Python commands:

```bash
make test                         # pytest tests/ -v
pytest tests/test_segment_merger.py -v
pytest tests/test_segment_merger.py::TestSegmentMergeIntegration::test_merge_creates_continuous_audio -v
make lint                         # ruff check . and mypy .
make format                       # ruff format . and ruff check --fix .
make validate                     # python scripts/validate_config.py
```

`run_all_tests.sh` also runs coverage and writes an HTML report to `htmlcov/`.
The test configuration is in `pyproject.toml`; tests are discovered from
`tests/` with `test_*.py` names. Most tests use temporary database, audio, and
Obsidian paths from `tests/conftest.py`, so avoid coupling unit tests to a real
`DATA_ROOT`.

The dashboard frontend is a separate Vite project:

```bash
cd web/frontend
npm ci
npm run lint
npm run build
npm run dev
```

For an operational Docker deployment, configure `DATA_ROOT` in `.env` and use
`./vj-control.sh start|stop|restart|status|logs`. Configuration validation and
batch behavior are documented in [docs/CONFIG_REFERENCE.md](../docs/CONFIG_REFERENCE.md)
and [docs/SCHEDULER_BEHAVIOR.md](../docs/SCHEDULER_BEHAVIOR.md).

## Architecture

Voice Journal is a local, CPU-oriented audio journal. The active runtime is a
two-part pipeline:

1. `daemon_v2.py` starts lightweight real-time capture and VAD components.
   `audio_capture/` reads mono 16 kHz microphone audio; `vad/` uses Silero VAD
   to identify speech and `processing.batch_processor.StagingQueue` writes
   compressed staged segments plus JSON metadata.
2. `BatchScheduler` processes the staged backlog between chunks. During the day
   it waits for the configured CPU-idle period; during the 22:00–06:00
   Asia/Kolkata guaranteed window it processes continuously. It selects the
   fallback ASR model when the backlog exceeds the configured overflow.
3. `BatchProcessor` merges adjacent VAD segments, preprocesses audio, runs
   faster-whisper through `asr/`, optionally identifies speakers, groups
   conversations, classifies them, and writes outputs.
4. `storage/` maintains SQLite metadata and an optional FTS5 index. The
   Obsidian output layer writes daily and conversation notes; dashboard audio
   is cached separately from staging audio.
5. `web/app.py` serves the Flask API and the built React SPA in
   `web/frontend/`. API responses and playback read from SQLite and the
   configured cache. Health endpoints are unauthenticated; dashboard/API
   routes use HTTP Basic Auth configured through environment variables.

The primary configuration is `config/default_config.yaml`, loaded through
`config/settings.py`. Paths are normally rooted under `DATA_ROOT`; the
`VJ_` environment-variable prefix can override nested settings. Preserve
`Asia/Kolkata` date handling when changing storage, scheduling, or transcript
logic.

## Repository Conventions

- Keep capture/VAD work lightweight and near-real-time. Expensive operations
  (ASR, preprocessing, speaker identification, grouping, classification, and
  note generation) belong in the batch path rather than audio callbacks.
- Treat the staging directory and SQLite backlog tracker as the handoff
  contract between capture and batch processing. Staged audio has adjacent JSON
  metadata and must remain recoverable after a restart.
- Segment merging is intentional: gaps below
  `segment_merging.merge_gap_seconds` are merged, transcription units are
  bounded by the configured minimum and maximum durations, and near-silent
  units may be skipped by preprocessing.
- SQLite writes go through the storage layer. Keep schema migrations and FTS5
  trigger/index maintenance compatible with existing databases; do not assume
  a fresh database.
- Audio is mono at 16 kHz. Runtime staging uses Opus where possible and has a
  WAV fallback when ffmpeg conversion fails. Keep temporary audio files and
  cache paths outside source-controlled directories.
- Hindi/English code-switching is supported by leaving `asr.language` as
  `null` unless a task explicitly requires forced-language transcription.
  Voice profiles must be calibrated before relying on speaker identification.
- The frontend talks to the Flask API rather than directly to SQLite or the
  filesystem. Keep API route/auth behavior in `web/app.py` and React API
  access centralized in `web/frontend/src/lib/api.ts`.
- Use the existing project formatting settings: Black/Ruff line length is 100,
  Ruff targets Python 3.10, and frontend code follows the existing
  TypeScript/React/Tailwind structure.
- Do not commit recordings, model files, generated caches, local databases,
  credentials, or `.env` values. Operational storage belongs under the
  external `DATA_ROOT`; inspect deployment docs before changing Docker mounts
  or system-service behavior.

## Operational References

- [README.md](../README.md) covers Docker deployment, storage layout, services,
  migration, and troubleshooting.
- [CONTRIBUTING.md](../CONTRIBUTING.md) covers the development setup and code
  style.
- [CLAUDE.md](../CLAUDE.md) contains the project’s local quick-start,
  calibration, deployment, and language-support notes.
