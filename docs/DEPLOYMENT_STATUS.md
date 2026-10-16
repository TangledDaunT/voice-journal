# HP Docker deployment — 2026-10-15

Deployed the local stabilization source at approximately 22:40 Asia/Kolkata.

Dashboard (Tailscale required):
https://shreyansh-hp-laptop-15-da0xxx.tail6e6a7a.ts.net/

Authenticated HTTPS dashboard, JavaScript, and CSS each returned 200.
Unauthenticated dashboard returned 401. Local `/health`, `/api/storage`,
`/api/conversations`, `/api/days`, and `/api/stats` returned 200;
health reported the existing 19 conversations and connected database.

The running containers are `voice_journal_daemon` and `voice_journal_web`, using
`voice-journal:stabilized-20261015`. Both had zero restarts at verification;
web was healthy. Release source and configuration are under
`/home/shreyansh/voice-journal-release-20261015/` on HP. Compose project:
`voice-journal-stabilized`. Manage this deployment with:

```sh
cd /home/shreyansh/voice-journal-release-20261015
docker compose -p voice-journal-stabilized -f compose.yml ps
# To stop/start this release:
docker compose -p voice-journal-stabilized -f compose.yml stop
docker compose -p voice-journal-stabilized -f compose.yml up -d --no-build
```

The previous containers are stopped and retained as
`voice_journal_daemon_before_20261015` and `voice_journal_web_before_20261015`.
The previous source checkout is unchanged. Its old control script targets the old
Compose configuration; use the release commands above for this deployment.
Existing HTTP Basic Auth credentials were securely preserved without printing
them. The source-only image reused existing dependencies; no model downloads
were performed. Model caches were copied to the external drive.

The existing nested host data root was deliberately preserved:
`/mnt/music-drive/voice-journal/voice-journal` mounted at `/data`.
No recordings or staged audio were moved/deleted. A SQLite backup was made at
`/mnt/music-drive/voice-journal/voice-journal/voice-journal/backups/before-deploy-20261015.db`.
A future path normalization must be a separate migration.

The HP was on battery. Deployment adds a basic battery guard before model loading,
at scheduler entry, and between ASR units. Transcription waits for AC; capture
continues. This does not interrupt an already-running ASR call. Local ASR threads
are capped at two; deployment uses the small fallback model and disables all-day
processing. Daemon limits: 1 CPU, 2 GiB. Web: 0.5 CPU, 512 MiB.
Observed running snapshot: daemon 0.72% CPU / 709.9 MiB, web 0.01% / 41.87 MiB.
These are idle/capture observations, not active ASR benchmarks.

After adding the deployment battery guard, tests reported **61 passed, 3 skipped**
(`/tmp/vj-deploy-tests.log`). Earlier AUDIT.md statements about the battery guard
being entirely absent are superseded by this limited implementation. Groq routing,
full speaker identification, and the other unfinished upgrade phases remain
unfinished. This deployment is the stabilization release, not the full upgrade.

## Groq-first release — 2026-10-15, approximately 23:15 Asia/Kolkata

Supersedes the stabilization deployment above. Active release directory on HP:
`/home/shreyansh/voice-journal-groq-20261015`; image
`voice-journal:groq-live-20261015`; Compose project remains
`voice-journal-stabilized`. Manage it from the **new** directory:

```sh
cd /home/shreyansh/voice-journal-groq-20261015
docker compose -p voice-journal-stabilized -f compose.yml ps
docker compose -p voice-journal-stabilized -f compose.yml up -d --no-build
```

The old source checkout, old images, and original pre-stabilization stopped
containers remain available for rollback. Existing recordings, authentication,
and the intentionally nested external-data path were preserved. A database backup
was taken before deployment. No real API key was put in source, an image, database,
API response, or logs; it is in protected server `.env` files (mode 0600), injected
into the containers. Settings show only configured status and a connection test.

### Diagnosis and fixes

The microphone had a real input signal (~-22.8 dBFS in a two-second check), but a
file containing `unmuted` existed. Capture treats presence of that file as mute,
while the old API treated its **contents** as state. Thus the UI said unmuted
while every recording callback discarded audio. Unmuting now **removes** the
file; mute status uses existence consistently. API and capture regression tests
cover this. The contradictory live flag was removed.

Three old staged audio/JSON pairs were all zero bytes. Their invalid JSON made the
old backlog endpoint return a misleading zero. They were preserved under
`audio/quarantine/`, not replaced with invented audio or timestamps. The dashboard
reports their count separately. JSON staging writes now use fsync and atomic rename.

The detail API also had a missing success response introduced during stabilization.
It now returns 200 for real notes and 404 for absent notes. React uses route IDs to
fetch/open the actual note, including direct links from recent conversations.
Original and enhanced recordings are playable separately. Existing legacy cached
audio is enhanced on demand. Raw transcript wording is never rewritten by an LLM.

Dark/light/system controls now share one provider, apply CSS variables globally,
and persist in local storage. Header theme and mute controls work across pages.
The dashboard and settings have updated colors/layout, truthful telemetry, dated
journal sections, and responsive controls. Route bundles are lazy-loaded; entry JS
is about 352 kB and the separately loaded dashboard/chart chunk about 377 kB.

### Processing behavior

Microphone/VAD stays separate from networking and ASR. Approximately six seconds
of incoming audio are checked for speech, then completed speech clips are processed
immediately by the worker. Groq `whisper-large-v3` is primary, including on battery.
This is frequent short-clip transcription, **not word-by-word websocket streaming**.
Latency includes the capture interval, API time, and any queue/quota delay.

On Groq authentication/network/rate-limit/other failures, only local faster-whisper
is used as fallback. It runs on AC, with two CPU threads and nice 19. On battery
when cloud is unavailable, audio remains queued until cloud recovers or AC returns;
no audio is dropped. The dashboard states this explicitly. Local ASR does not run
inside capture callbacks. Partial/in-flight calls are not forcibly cancelled.

Usage is reserved durably before each upload, storing actual audio seconds and
`max(10, audio_seconds)` billed seconds separately. Conservative configured limits
are 20 requests/minute, 2,000/day, 7,200 billed audio seconds/hour and 28,800/day,
with a 90% safety budget. Only rate-limit response headers are retained; 429
Retry-After creates a persisted cooldown. Failed/uncertain requests are counted
conservatively. Short clips consume the ten-second minimum and can exhaust request
limits earlier than total audio duration suggests. Limits are organization-wide;
this app cannot account for usage by other applications sharing the Groq account.

Original recordings are preserved. Playback enhancement uses high-pass/low-pass,
FFmpeg spectral noise reduction, and loudness normalization in a separate cache.
It can reduce steady background noise; perfect source separation or removal of all
noise/overlapping voices is not promised. Silence, confidence and repetition checks
retain raw ASR payloads and mark questionable notes for review.

References checked during implementation:
[Groq speech-to-text](https://console.groq.com/docs/speech-to-text) and
[Groq rate limits](https://console.groq.com/docs/rate-limits).
Enable **Zero Data Retention** in the Groq console Data Controls yourself; this
application has not verified that it is enabled.

### Data controls

- Export CSV: `/api/data/export.csv`, sorted by date/start time.
- Export full archive: `/api/data/export.zip`, including CSV, a SQLite snapshot,
  recordings and derived audio. Credentials/model caches are excluded.
- Blank CSV header template: `/api/data/template.csv`.
- Import: authenticated multipart POST `/api/data/import`, file field `file`;
  UTF-8 CSV, max 5 MB / 10,000 rows. Required columns:
  `date,start_time,end_time,text`. Optional: `language,speaker,engine`.
  Dates are strict YYYY-MM-DD; same-day times use local Asia/Kolkata time.
  Validate the whole file before writing; transactions prevent partial imports.
  Reimporting identical entries skips duplicates. Imported text is clearly marked;
  CSV alone does not attach or fabricate audio.
- Clear: authenticated POST `/api/data/clear` with JSON
  `{"confirmation":"DELETE ALL USER DATA"}`. The UI requires that exact phrase.
  Deletes journal rows, recordings, audio caches, imports, exports, application
  backups, calibration/runtime user data and validation copies. SQLite file and
  schema remain; FTS triggers stay consistent and new imports/capture still work.
  Authentication/Groq environment configuration and reusable model weights remain.
  Clear and processing share a cross-process lock; pre-clear captured buffers are
  excluded using a reset epoch. New speech after clearing can create new notes.

Clear-all was tested **only in temporary storage**, never against the live journal.

### Verification evidence

- Local `PATH=/tmp/voice-journal-audit-py313/bin:$PATH make test`:
  **72 passed, 3 skipped** (`/tmp/vj-live-tests.log`).
- `npm --prefix web/frontend run lint` and `npm --prefix web/frontend run build`:
  passed (`/tmp/vj-live-lint.log`, `/tmp/vj-live-build.log`).
- Ruff on the five new runtime modules and new tests: passed.
- Repository-wide `make lint` still fails on **723** diagnostics, including existing
  legacy-code issues; no claim of repository-wide lint success is made.
- Browser checks against the real HTTPS deployment: dark mode persists after reload;
  light mode switches; Groq test succeeds; a real Groq note opens by direct URL;
  original and noise-reduced audio return HTTP 206; browser playback time advances;
  dashboard renders; CSV export succeeds; unauthenticated export returns 401;
  390px mobile settings has no horizontal overflow; no browser runtime errors.
  Output: `/tmp/vj-browser-final.log`. Screenshots of settings:
  `/tmp/vj-settings-dark.png`, `/tmp/vj-settings-mobile.png` (on the Mac).
- Live database observed **9 Groq segments**: 8 ok, 1 low-confidence. All **10**
  real transcription calls returned HTTP 200, including one isolated verification
  request. Actual raw audio usage: 36.942 seconds; billed minimum accounting:
  100 seconds. Counts may increase as real speech continues.
- An eight-second existing recording was transcribed through the actual Groq
  endpoint: 19 words, saved source/enhanced files, processing time **1.4 seconds**.
  This used a separate validation DB, not fabricated dashboard data. Its real API
  usage was transferred into production usage accounting and verification copies
  were removed afterward. No transcript contents were printed.
- Latest observed production save took **1.46 seconds** after its clip was staged.
  The capture interval is additional, so this is not an end-to-end latency claim.
- Capture telemetry showed increasing chunk counts, live input around -25 dBFS,
  active/unmuted stream, fresh timestamps and zero capture errors. A zero queue
  now means no completed speech clips are waiting; it does not by itself prove
  microphone health or transcription success. Use the live level/last-save panel.
- Actual local-model fallback benchmarking was skipped because HP was on battery.
  Failure-to-local routing and persistence were tested with a controlled local
  transcriber in temporary storage, including cloud-on-battery and outage-on-battery.
  No claim of measured local accuracy/speed is made.

This release still does not implement the earlier full embedding diarization,
Hermes view/CLI package, word-by-word streaming, or all seven upgrade phases.

Final live snapshot: **13 Groq segments saved**, all **14** real transcription
requests HTTP 200 (including the one accounted verification request). The current
capture session showed 714 received chunks, 4 detected/staged segments and zero
capture errors; the other saved segments came from the preceding release process
before its final recreation. At this snapshot the microphone was **muted**; that
state was respected rather than overridden. Use the top-bar Unmute control to
resume. Idle/capture resource snapshot: daemon 1.33% CPU / 177.1 MiB; web 0.01%
CPU / 58.57 MiB. Values are point-in-time observations, not ASR benchmarks.


## Enrolled-voice filter release — 2026-10-15, 23:42 Asia/Kolkata

This section supersedes the active release path above. Running source:
`/home/shreyansh/voice-journal-speakers-20261015`; image:
`voice-journal:enrolled-voices-20261015`. The Compose project and container names
are unchanged. Manage this deployment with:

```sh
cd /home/shreyansh/voice-journal-speakers-20261015
docker compose -p voice-journal-stabilized -f compose.yml ps
docker compose -p voice-journal-stabilized -f compose.yml up -d --no-build
```

Existing data, protected credentials, Groq configuration and mounted cache paths
were preserved. A pre-release SQLite backup is in
`/data/voice-journal/backups/before-speaker-filter-20261015.db` inside the container.
The external drive was verified as `/dev/sdb1`, exFAT, mounted at
`/mnt/music-drive`, with 444 GiB available. Both containers have zero restarts;
web is healthy. Observed idle snapshot with normal journaling muted and no
profiles: daemon 0.99% CPU / 159.9 MiB (2 GiB limit), web 0.01% / 56.67 MiB
(512 MiB limit). These are not active-ASR resource measurements.

### Filtering and calibration

Open `/calibration`. Choose Calibrate Shreyansh, Calibrate Shivangi, or enter
another person's name. One person speaks for 30 seconds, near the HP for the
first 10 seconds, walking and speaking for the next 10, then farther away for
the last 10. Pause all media and ask others to stay quiet. Uses the existing HP
microphone stream, including when the page is open on another device. Countdown
comes from captured sample count, not elapsed browser time. Normal journaling is
paused during enrollment, and its mute state is preserved. Calibration explicitly
receives audio even when ordinary capture is muted. Recalibrating the same name
replaces its reference. Profiles may be disabled in the calibration page.

The local bundled Resemblyzer 0.1.4 encoder creates 256-dimensional embeddings;
no cloud request or paid model is used for enrollment or matching. Up to three
position references are saved in SQLite. Raw enrollment WAV is removed after
analysis. Too little speech, clipping or inconsistent samples fail with a retry
message. These checks do not measure identity accuracy.

Default `speaker.enrolled_only: true` blocks transcription until a voice is
enrolled. Every new/unprocessed segment is checked before Groq or local Whisper.
Overlapping two-second windows must agree; cosine similarity must reach 0.80,
with a 0.08 lead over the next enrolled person. Accepted contiguous speech must
be at least 1.6 seconds. Only matched time ranges are sent to ASR, with original
wall-clock offsets preserved. Resulting journal rows carry the speaker name,
profile ID and similarity. Unknown/ambiguous ranges are not transcribed; original
source clips and a decision ledger remain locally under `audio_filtered` for
review/export. No new profile means staged audio remains pending. Existing notes
are preserved and are not automatically relabeled. Manual batch paths use the
same gate. Encoder failures block transcription rather than bypassing the gate.

Voice matching is probabilistic. Very short phrases, distant/quiet speech,
overlap and poor calibration may be skipped. A recording of an enrolled person's
voice can match, and mixed media plus an enrolled voice may pass together.
A single room microphone cannot guarantee live-versus-replayed speech detection
or clean separation of simultaneous sources. No accuracy percentage has been
measured for Shreyansh/Shivangi; their real enrollments are still required.
Resemblyzer is strongest on English; Hindi/code-switching requires real testing.

Wispr's public material describes the desired behavior but does not publish a
reproducible implementation of its proprietary filtering. This is an independent
speaker-verification implementation, not a reproduction of that algorithm.
Primary references: [Wispr live transcript documentation](https://docs.wisprflow.ai/articles/4091106439-The-live-transcript-in-Notetaker),
[Resemblyzer](https://github.com/resemble-ai/Resemblyzer), and the distinct
[target-speaker separation problem (VoiceFilter)](https://arxiv.org/abs/1810.04826).

Clear-all removes enrolled profiles and filter decisions as well as journal data,
while retaining the SQLite file/schema. Full archive export includes the SQLite
backup (with profiles) and locally retained filtered source audio. CSV remains
for dated transcript rows, not voice-biometric enrollment.

### Validation and remaining manual checks

Commands run locally:

```sh
PATH=/tmp/voice-journal-audit-py313/bin:$PATH make test
npm --prefix web/frontend run lint
npm --prefix web/frontend run build
git diff --check
```

Results: **83 passed, 3 skipped**; frontend lint/build passed; diff whitespace
clean. New modules also pass targeted Ruff and Python 3.10 syntax parsing. Whole
repository lint retains earlier documented failures; do not claim it is green.
Temporary tests cover identity matching/rejection/ambiguity, cropped uploads,
no-profile/no-cloud behavior, exact 30-second capture, cancellation, enrollment
API and profile removal. Synthetic test embeddings are never deployed as people.

Live browser verification used `/tmp/vj-speaker-browser.cjs` and
`/tmp/vj-speaker-regression.cjs`, with credentials captured privately in memory.
The HP stream delivered 2.048 seconds in a deliberately cancelled calibration;
normal mute remained true and no voice profile was created. Calibration renders
at desktop and 390px mobile widths without horizontal overflow or browser errors.
Existing note detail returned 200, original and enhanced audio returned 206 and
browser playback advanced; theme persistence, dashboard, dated CSV export and
unauthenticated 401 checks passed. No production data was cleared/imported for
testing. After deployment Groq usage remained 28 requests / 71.92 audio-seconds /
280 billed-seconds, with zero enrolled profiles and `enrollment_required` status.
The HP microphone stream is active; ordinary journaling is currently muted.

An actual encoder probe on existing unlabeled audio saved no profile and assigned
no identity. Four separate two-second embedding calls took 4.331, 0.196, 0.186,
0.197 seconds; warm mean 0.193 seconds/window. The whole independent probe process
used 417.3 MiB RSS. Initial imports/JIT have a cold-start cost. This is an encoder
speed check, not recognition accuracy, full pipeline latency or local ASR speed.
No paid calls/model downloads were required for this speaker release.

User acceptance still required: enroll each real voice, unmute normal journaling,
test each voice near/far, test reel/movie rejection with both people silent, and
test speaker changes/overlap. Accuracy and false accepts/rejects must be assessed
from those recordings; no such success is claimed in advance.

## Continuous conversations and dashboard listening — 2026-10-16

Active release: `/home/shreyansh/voice-journal-continuous-20261016` on HP.
Image: `voice-journal:continuous-20261016`. Compose project remains
`voice-journal-stabilized`; containers remain `voice_journal_daemon` and
`voice_journal_web`. Manage from the new directory using `compose.yml`.
The prior enrolled-voice release/image remains available for rollback.

The existing nested external-drive mount and protected environment files were
preserved. `/dev/sdb1` (exFAT) was mounted at `/mnt/music-drive`, with 444 GiB free.
A SQLite snapshot was made before deployment at
`/data/voice-journal/backups/before-continuous-20261016.db` inside Docker.
No production records, profiles, imports, recordings or old quarantined queue
items were cleared. No Hermes files/databases were accessed.

See [CONTINUOUS_CAPTURE.md](CONTINUOUS_CAPTURE.md) for diagnosis, precise silence,
chunk/context/conversation rules, transcript ownership, playback assembly,
language policy, live listening and manual acceptance steps. Journal list/search
now batch-load segment provenance and avoid legacy audio scans for known sources.

Actual HP audio inspection found no USB microphone. The external analog mic jack
was present (`Mic Jack=on`) on the PCH / Realtek ALC236 card. Codec capture mixer
0x23 selected external node 0x19; its internal mic connection was muted. Capture
and enrollment now share the named `vj_external` PCM, which pins
`hw:CARD=PCH,DEV=0` through an ALSA plug for 16 kHz mono conversion.
`asound.conf` is mounted read-only in both containers. A named ALSA jack guard
blocks queue-thread audio delivery on disconnect/missing controls instead of
allowing built-in fallback. Actual selected input and disconnect errors appear
on the dashboard/calibration page. Physical unplug/replug was not performed.

All six historical Urdu/Japanese/Russian clips inspected were captured before
the 23:42 speaker-filter release on 15 October. Their preserved originals decode
successfully: durations 0.778–2.516 seconds, RMS approximately −23.8 to −18.1 dBFS,
with WebRTC speech detection finding 0.75–2.49 seconds per clip. Confidence alone
accepted some unexpected outputs, including Urdu at average log probability −0.064.
This establishes available, non-silent source audio and the old validation gap;
it does not establish the true spoken wording or who/what produced those sounds.
Historical text/audio is preserved and unexpected language/script is flagged.

Live listening uses authenticated dashboard controls and the daemon's existing
stream, including while journaling is muted. An initial file-based probe stalled
on exFAT metadata/fsync; it was replaced with a bounded shared RAM buffer through
the existing shared Docker IPC namespace. All persistent journal data and runtime
state remain on the external drive. The temporary files from the initial probe
were removed. No cloud transcription was needed for listening verification.

Validation on temporary data: **104 passed, 3 skipped**, including a 50-second
synthetic pipeline test producing one conversation with exactly ordered words,
word overlap ownership, sample continuity, speaker turns/gaps, continuous WAV
playback, migration from the old unique schema, both language retry paths,
missing device rejection, authenticated listening routes and expired/stopped
listeners. Tests explicitly default to AC/no battery, so results do not depend
on whether the developer's Mac is plugged in; battery tests override this.
Frontend ESLint and TypeScript/Vite build passed. Targeted Ruff and diff whitespace
checks passed. Repository-wide lint was not rerun; its pre-existing failures are
not claimed fixed. Logs on the Mac: `/tmp/vj-continuous-tests.log`,
`/tmp/vj-continuous-lint.log`, `/tmp/vj-continuous-build.log`.

The deployed browser decoded and scheduled eight real HP PCM buffers (2.048 s),
and a separate 8,236-byte live WAV measured about −24 dBFS. Stop returned 204 for
further audio; an abandoned eight-second lease also expired. Normal journal mute
and daily Groq accounting were unchanged. Browser playback verification is not a
claim that a human listened to or recognized speech in the room.

Real voice profiles remain absent; transcription correctly reports
`enrollment_required`. Normal journaling remains muted. Enroll each person for
30 seconds (10 seconds near, 10 walking, 10 farther away), then unmute and speak
for 30–60 seconds in Hindi/English/mixed speech with brief pauses and speaker
changes. Compare text and joined playback, test media rejection with both people
silent, and physically unplug/replug the mic. Real recognition/filter accuracy,
physical disconnect behavior and local-model speed are still user acceptance
checks; no invented profile, production test transcript or claimed accuracy was
introduced.

A late acceptance check exposed an existing native talkback write/close race:
web exited with signal 139 while concurrent Audio Test talkback requests were
active. Start, write, status and stop now share a lock so a native stream cannot
be closed during an in-flight write. A controlled concurrent test passed, and
8 real native-output start/write/stop cycles with silent PCM passed (27 writes
completed, 5 correctly rejected after Stop). Calibration now also refuses a
reported external-mic disconnect immediately. Legacy audio directory listings
are batched per date to avoid one external-drive directory scan per card.

The final browser verification also passed historical review flags (6 entries),
existing original/enhanced HTTP 206 playback with advancing playback time,
calibration rendering, dark/light persistence, dated CSV export, 390px dashboard
layout, unauthenticated 401 checks and no browser runtime errors. Screenshot:
`/tmp/vj-continuous-dashboard.png`; sanitized browser log:
`/tmp/vj-continuous-browser.log`. A timeout diagnostic had exposed a Basic Auth
header in this chat; its saved log was sanitized and password rotation was
recommended. No credential values were added to source or deployment docs.

Read-only integrity check: `ok`; production has 55 conversations, 27 source
provenance rows, zero speaker profiles and 28 all-time Groq request records.

Final repeat verification passed against the last deployed image, including live
HP audio after the talkback fix. Both containers are running with zero restarts
for this final deployment; web is healthy. The expired live shared RAM header
was verified cleared. Production and pre-deployment backup counts match exactly:
55 conversations / 27 provenance rows / 0 profiles / 28 Groq requests. Normal
journaling remains muted. Final idle snapshot was about 155 MiB daemon / 56 MiB
web; these are not active-ASR measurements.

## Capture recovery after real enrollment — 2026-10-16, approximately 02:30 IST

Both real 30-second profiles, Shreyansh and Shivangi, were successfully saved and
enabled. Normal capture was unmuted, but no new audio had been staged. Diagnosis
used the actual process stacks and the exception log: the sole VADWorker died
when idle `_flush_continuous()` timed out on `data_lock` during the first real
encoder/enrollment operation. That flush ran inside a `queue.Empty` exception
handler, so the later exception handlers did not catch its TimeoutError. The
bounded downstream queue then filled and blocked the capture delivery thread.
Main-thread heartbeat and open PortAudio stream falsely looked healthy.

Before restarting, 6,578 queued PCM chunks (1,683.968 sample-seconds, about 28
minutes) were preserved under `audio/recovery/capture-stall-20261016/` on the
existing external drive. A manifest preserves chunk-group timestamps and WAV
files; 4,880 discontinuous groups reflect the stalled capture/overflow situation.
This is available captured audio, not a claim that every word or a continuous
28-minute conversation survived. Original files remain as a recovery copy; do
not reimport them blindly and duplicate the normal queued processing.

The running consumer was repaired without first discarding its memory queues;
actual enrolled-speaker checks and Groq saves resumed. Queues subsequently caught
up to current capture. Capture was briefly paused for a controlled drain before
recreation: raw queue=0, VAD queue=0, continuous samples=0. Staged backlog remains
on disk and continues through the original speaker gate and Groq/local policy.
Neither profiles nor production data were cleared or replaced.

Persistent release: `/home/shreyansh/voice-journal-recovery-20261016`, image
`voice-journal:capture-recovery-20261016`, same Compose project and containers.
Protected `.env`, pinned microphone configuration, external paths and resource
limits remain. Timeout handling now surrounds idle/active paths, retains audio
for retry, and skips idle data-lock acquisition when no audio exists. A watchdog
restarts an unexpectedly dead VAD consumer. Runtime status exposes consumer
liveness, queue depths, input overflow counts and stalled delivery; UI no longer
relies only on heartbeat/stream-open state. Callback logging/filesystem mute
checks moved out of the hardware callback, and ALSA library discovery is cached
rather than repeatedly launching discovery for every chunk.

A second display bug sorted conversations only by time-of-day. List and latest-ID
queries now sort by date before time, so today's early-morning notes appear before
yesterday's late-night notes. Dashboard conversation refresh is five seconds.

Validation: **109 passed, 3 skipped**; frontend lint/build and targeted Python lint
passed. New tests reproduce the idle lock-timeout crash, retained-buffer retry,
empty flush during enrollment, dead-consumer recovery and cross-midnight journal
ordering. Real Groq saves were observed after repair; no synthetic production
transcripts or profiles were inserted. Recovery may contain gaps from the earlier
overflows; recognition accuracy still depends on the actual captured speech.

Final recovery verification: both consumer threads alive, audio delivery increasing,
external PCM selected, normal journaling unmuted, both real profiles enabled.
Browser latest-list check returned today's date first and real Groq entries;
dashboard listening, recovered note detail and original HTTP 206 playback passed.
At the read-only snapshot, recovery had created 49 source segments across 14
conversations today (45 Groq ok, 3 Groq low-confidence, 1 local low-confidence).
All pre-incident provenance IDs remain. Older staged audio is still processing;
Groq safety budgets remain enforced and local fallback can slow backfill on AC.
ASR quality/identity for every recovered word has not been independently verified.
Evidence: `/tmp/vj-recovery-tests.log`, `/tmp/vj-recovery-lint.log`,
`/tmp/vj-recovery-build.log`, `/tmp/vj-recovery-browser.log` on the Mac.

## Audio continuity repair — 2026-10-16, 02:49 IST

Active release: `/home/shreyansh/voice-journal-audiofix-20261016`; image
`voice-journal:audio-continuity-20261016`, Compose project `voice-journal-stabilized`.
Both services are healthy/running. Production data, models and logs remain on the
external disk. Capture was stopped and fully drained (both queues and continuous
samples zero) before restart. External SQLite backup:
`backups/before-audiofix-20261016.db`. Dashboard credentials were preserved privately.

See [AUDIO_CONTINUITY_AUDIT.md](AUDIO_CONTINUITY_AUDIT.md) for the five frozen samples,
measured playback gaps, prompt contamination and verification. Changes include
independent capture/media locks, lossless FLAC staging, ADC clock timestamps,
0.5-second input buffering, one-thread local ASR, minute pacing deferral, prompt
removal/review flags, gentler enhancement and authenticated full-source playback.
Voice verification remains mandatory for transcription; full playback can contain
unverified voices. Old recordings/transcripts remain intact.

Validation: **115 passed, 3 skipped**, frontend lint/build passed. All five original
and full audio routes returned HTTP 206; both playback modes advanced in Chrome;
anonymous full playback returned 401. A real 37.22-second local ASR check had zero
new capture overflows and empty capture queues. A separate 45-second browser check
also had zero new overflows. Both enrolled profiles remain enabled; SQLite
quick_check ok; fresh lossless files observed externally. No claim of direct
listening or word-level recognition accuracy: this session cannot perceive audio.

## External-drive recovery, public proxy and microphone studio — 2026-10-16

Active release: `/home/shreyansh/voice-journal-studio-20261016`.
Daemon image: `voice-journal:microphone-studio-20261016`.
Web image: `voice-journal:microphone-studio-ui-20261016` (adds permission cancellation
and timeout guidance). Same Compose project; web joins nginx-proxy-net persistently.
Public URL: https://voice.tangleddaunt.dpdns.org, existing login retained.

A USB disconnect at 02:58:34 broke the external drive bind mount; known UUID
6EFF-790D was remounted at /mnt/music-drive and containers recreated. DB quick_check
ok; both profiles retained. Drain before studio deployment was verified empty;
external backup `backups/before-studio-20261016.db` was saved. Later UI-only restart
did not restart capture. No filesystem repair/formatting was performed.

`voice-journal-recover.timer` is enabled, checks every 30 seconds and recovers only
the journal's known mount/services. Maintenance marker: /run/voice-journal-maintenance.
Active release pointer: /etc/voice-journal-release. Do not restart the previous
release or omit the proxy network on future deploys. See MICROPHONE_STUDIO.md.

Studio includes HP native gain/boost, HP and local Mac/PC monitoring, saved EQ/gain,
voice filters, compressor, output limiter and presets. Software processing applies
to monitoring and future enhanced recordings; originals/ASR remain unchanged.
Mac monitoring is browser-local, requires OS/browser permission, and is not global
Mac microphone processing. Physical Mac input was not verified: native capture
remained permission-pending in automation; synthetic MediaStream flow and cleanup
passed. HP live audio through the public domain was verified with actual signal.

Validation: **128 passed, 3 skipped**, frontend lint/build passed; settings/auth and
native HP control read/write checks passed. Public HP stream and live EQ update
passed; last observed capture overflows zero, queues empty and consumers alive.
