# Voice Journal stabilization audit — 2026-10-15

This is an initial Phase 0 stabilization pass, not completion of the seven-phase
upgrade. No production files, recordings, transcripts, database rows, or Hermes
files were changed. No model downloads or paid API calls were made. Source review
focused on capture, staging, ASR, grouping, storage, API, frontend, configuration,
and deployment; this is not a claim that every repository file was read.

## HP evidence (read-only SSH, approximately 22:00 Asia/Kolkata)

Tailscale identified `shreyansh-hp-laptop-15-da0xxx` at `100.99.161.57`.

- `findmnt /mnt/music-drive`: `/dev/sdb1`, exFAT, mounted read/write.
- `df -h /mnt/music-drive`: 932G total, 487G used, 445G available (53% used).
- `free -h`: 7.7 GiB RAM total, 4.2 GiB used, 3.4 GiB available;
  2.0 GiB of 4.0 GiB swap used.
- `docker stats --no-stream`: daemon 0.56% CPU and 52.81 MiB/2 GiB;
  web 0.07% CPU and 55.2 MiB/1 GiB. These are single idle snapshots,
  not active ASR measurements or averages.
- Live `.env` DATA_ROOT is `/mnt/music-drive/voice-journal/voice-journal`.
  Both containers bind that source at `/data` and set DATA_ROOT=/data.
  Their configured DB is `/data/voice-journal/db/voice_journal.db`, hence the
  host DB is nested three `voice-journal` levels below `/mnt/music-drive`.
  The requested `/mnt/music-drive/voice-journal/db/voice_journal.db` is absent.
- Docker's live Hugging Face cache source is the repository's `hf_cache/`,
  on the internal disk. Local Compose now places it under the external cache.
- The actual live journal DB contains 19 conversation rows and 2 daily journals.
  `PRAGMA journal_mode` returns `delete`, not WAL.
- A SQLite URI connection with `mode=ro` rejected
  `CREATE TABLE __readonly_probe (id INTEGER)` with
  `attempt to write a readonly database`. No table was created.

Remote commands used: `tailscale status`; SSH `hostname`, `uptime`,
`findmnt /mnt/music-drive`, `df -h /mnt/music-drive`, `free -h`,
`docker stats --no-stream --format '{{.Name}} CPU={{.CPUPerc}} RAM={{.MemUsage}}'`;
Python reading only the DATA_ROOT line from the project's `.env`;
`docker inspect voice_journal_daemon voice_journal_web` parsed to print only
mounts, state, and DATA_ROOT; `docker exec -i voice_journal_web python -` loading
`Config.from_yaml('/app/config/default_config.yaml')` and opening that DB with
`sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)` for the aggregate queries
and write-denial probe below. No transcript contents or credential values were
included in the audit output. Remote Git status showed existing untracked files;
none was opened or modified.

## False-text findings

The live aggregate query searched raw text (legacy transcript fallback if the
column did not exist) for `thanks for watching`, `amara.org`, and
`use only hindi and english`, using case-insensitive SQL LIKE predicates.
18 of 19 conversations and 1 of 2 daily journals matched at least one phrase.
One group of conversation rows shared identical raw text longer than 20
characters. These counts identify candidates for review, not proven errors;
no audio was listened to and no text was deleted or rewritten.

1. **Prompt leakage risk.** The original `asr.initial_prompt` contained decoding
   instructions, including the exact language-control phrase found by the live
   query. `config/default_config.yaml:52` and `config/settings.py` now use vocabulary
   only. Evidence is consistent with prompt leakage during weak/silent inputs;
   acoustic verification is still required to establish the cause of each row.
2. **Derived text displayed as journal evidence.** ConversationCard,
   RecentConversations, and the Conversations detail page displayed summaries or
   cleaned text. They now show raw database text. `web/app.py:121`
   (`conversation_payload`) preserves raw text and marks known suspect phrases
   `suspected_hallucination`; the dashboard displays a Needs review badge.
   This is a conservative legacy warning, not the full per-utterance filter.
3. **Inconsistent search payload.** Search returned only id/date/time/summary
   although the frontend expected a full Conversation. List, detail, and search
   now share `conversation_payload` and retain database provenance.
4. **No fabricated conversation fixtures found** in the reviewed frontend/API.
   Form placeholders and calibration samples are legitimate interface text.
   Toast IDs use Math.random; no generated transcript data was found there.
   Local storage is used for preferences, not a discovered transcript fixture.
   Existing server-side recent-conversation collections are populated from SQL.
5. **Fabricated backlog duration.** `web/app.py` (`get_backlog`, formerly ~439)
   assumed every staged segment lasted 30 seconds. It now sums JSON metadata
   durations and reports invalid metadata as an error rather than guessing.

## Stabilization changes

- Python AST parsing found no indentation error in this checkout, including
  `processing/batch_processor.py`; none was fabricated or "fixed".
- Fixed root package initialization, which imported a nonexistent `voice_journal`
  package from this hyphenated checkout and prevented pytest execution.
  Heavy daemon imports are now lazy.
- `processing/batch_processor.py:437–499`: source acknowledgement moved after
  audio cache generation and SQLite commit. Failed/empty/silent work stays staged.
  A deterministic 48-bit source-group ID avoids counter collisions for new batch
  conversations. Grouping flushes at batch boundaries; see scheduler caveats.
  Added tests for both successful commit ordering and failed-commit retention.
- Cache creation failures now keep source audio queued. Zero retention days means
  keep forever and is the default. Fallback model config uses a deep copy.
- Enabled batch word timestamps; removed raw transcript text from batch ASR logs.
- `utils/storage_guard.py:11` checks the required mount, permissions, and destination
  containment without creating directories. Daemon/manual batch runtime paths
  call it before startup and staged/cache I/O. Internal class constructors retain
  an injectable guard for temporary-path tests; custom callers must supply it.
- `web/app.py:96`: read-only SQLite connections cannot create a missing DB.
  Removed schema/directory creation from daily journal reads. The storage status
  route returns 503 and the dashboard shows a persistent error banner when absent.
- Authentication now covers nested SPA routes, notes, assets, and all APIs except
  `/health` and `/api/health`. Removed embedded password defaults from API and
  Compose. Required variables: WEB_AUTH_USERNAME and WEB_AUTH_PASSWORD.
- `.env.example` pins DATA_ROOT=/mnt/music-drive. Removed control-script drive
  auto-detection. Compose data binds refuse to create missing source directories.
  The host control script must be used to verify the source is a mount; a Docker
  bind alone cannot prove its host source is the intended external disk.
- `scripts/validate_config.py` checks storage without creating fallback directories.
- Added ESLint config and corrected the 13 type/unused-variable violations it
  exposed. Existing frontend build still produces a large-bundle warning.

## Reproduction and validation

Local temporary environment (Python 3.12 from the bundled runtime; system Python
is 3.9 and unsuitable for this project):

```sh
/Users/shreyansh/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv /tmp/voice-journal-audit-py313
/tmp/voice-journal-audit-py313/bin/python -m pip install -q pytest ruff mypy numpy scipy pydantic pydantic-settings pyyaml loguru psutil flask flask-cors requests sounddevice python-slugify imageio-ffmpeg
```

A temporary `ffmpeg` symlink in that venv points to the imageio-ffmpeg executable;
this enabled actual Opus staging tests, rather than mocking encoding. No model
packages were installed. The `py313` environment name is just a directory label.
Initial attempts with system Python failed at Python 3.10 union syntax. Later
collection exposed missing python-slugify, then the broken root package import.
Before supplying ffmpeg, two existing staging tests failed with FileNotFoundError.

| Command | Final result |
|---|---|
| `PATH=/tmp/voice-journal-audit-py313/bin:$PATH make test` | 59 passed, 3 skipped |
| `PATH=/tmp/voice-journal-audit-py313/bin:$PATH make lint` | FAIL: 718 Ruff diagnostics; mypy not reached |
| `/tmp/voice-journal-audit-py313/bin/mypy .` | FAIL: checkout name `voice-journal` is not a valid Python package name |
| `npm ci --no-audit --no-fund` in web/frontend | 345 packages installed; dependency deprecation warnings |
| `npm run lint` in web/frontend | PASS |
| `npm run build` in web/frontend | PASS; main JS ~797 kB, gzip ~235 kB, >500 kB warning |
| `ruff check utils/storage_guard.py tests/test_storage_safety.py tests/test_batch_commit_safety.py` in that venv | PASS |
| `PATH=/tmp/voice-journal-audit-py313/bin:$PATH make validate` | FAIL: 9 issues, including missing model dependencies, missing mount, and unenrolled voices |
| `bash -n vj-control.sh` | PASS |
| `git diff --check` | PASS |
| AST parse changed runtime files with `feature_version=(3,10)` | PASS |

Baseline Ruff had 722 diagnostics. Repository-wide lint remains unfinished; no
blanket rule suppression was added. Initial frontend lint failed because there
was no ESLint config; after adding one, 13 existing violations were fixed.
The three skipped tests and full test output are in `/tmp/vj-test-final.log`.
Other session logs: `/tmp/vj-lint-before.log`, `/tmp/vj-lint-final.log`,
`/tmp/vj-mypy-final.log`, `/tmp/vj-frontend-lint-final.log`,
`/tmp/vj-frontend-build-final.log`, `/tmp/vj-validate-final.log`.

Built-bundle audit command (from web/frontend):

```sh
rg -l -i 'thanks for watching|amara\.org|use only hindi and english|mockData|demoData|sampleConversations' ../dist
```

No matches (exit 1). This is a targeted evidence check, not proof that arbitrary
future backend text is correct. Generic `sample`/`placeholder` matches include
legitimate microphone calibration and input attributes.

## Remaining work and limits

Phase 0 is not fully complete: broad lint cleanup, complete source review, live
row/audio verification, and physical missing-drive tests remain. No deployment
was attempted. Do not point production at a new empty path: nested existing data
needs a separately reviewed migration preserving staged audio and SQLite files.

Phases 1–6 are unfinished: Groq router/rate accounting and verified limits,
battery/thermal controls, calibrated embedding identification, durable utterance
statuses, Hermes schema/views/CLI, dashboard rebuild, runtime settings, waveform
peaks, resource benchmarking, and all associated acceptance checks. No Groq key
was requested or used. No realtime factor, speaker accuracy, embedding comparison,
active ASR CPU/RAM, or one-hour end-to-end result was measured.

The live DB is not WAL. Existing local VAD/model caches and some legacy tools
still need a complete external-storage audit. Physical unplug during an in-flight
write has not been tested; mount checks are not an atomic hot-unplug guarantee.
The default ASR thread count, CPU load guards, and mute confirmation remain to be
implemented/verified. The UI still includes legacy classification fields and
allows raw legacy rows without segment-level provenance. Raw text is retained
for review; it may contain hallucinations. No claim is made that all false text
has been fixed or that every dashboard line has a segment ID and playable audio.

Only the write-denial part of Hermes acceptance was proved on the live DB; the
10 queries/views do not exist yet. No Hermes agent database or code was accessed.


## Superseding deployed work — 2026-10-15

The earlier “No deployment / no Groq / speaker ID unfinished” statements describe
the initial audit only. See the latest sections in DEPLOYMENT_STATUS.md for the
subsequent Groq-first and enrolled-speaker releases, actual verification commands,
83-test result and remaining limitations. The calibrated Resemblyzer gate is now
implemented and deployed ahead of ASR, with a real 30-second HP enrollment flow.
No real person has been enrolled automatically. No real speaker accuracy, replay
rejection guarantee, overlap separation or full Hermes schema is claimed.
