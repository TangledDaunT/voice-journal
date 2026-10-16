# Five-conversation audio audit — 16 October 2026

The sample was frozen at the start of the investigation. Backfill can subsequently
extend the same conversations, so their current dashboard duration may differ.
Times are Asia/Kolkata. Private audio, provider responses and transcript comparisons
are retained only in the HP external validation directory, not in this repository.

| Conversation | Start–end | Audited duration | Verified audio retained | Timeline gap outside verified spans |
|---|---|---:|---:|---:|
| 117991299196737 | 02:05:38–02:06:33 | 55.24 s | 34.01 s | 21.23 s |
| 35013081255094 | 02:04:49–02:05:25 | 35.77 s | 17.43 s | 18.34 s |
| 257752234018170 | 02:04:43–02:04:50 | 6.14 s | 6.14 s | 0 s |
| 47480196107975 | 02:01:12–02:04:29 | 197.36 s | 104.45 s | 92.91 s |
| 120432764129423 | 02:00:44–02:00:55 | 10.91 s | 10.14 s | 0.77 s |

## Evidence and causes

- The existing “Original” player contained verified speaker crops, assembled on
  their timestamps with zero-filled gaps. It was not an unfiltered recording.
  Source clips retained before the gate contain additional room audio. Gaps at
  crop edges account for substantial apparent mid-sentence cutouts.
- Capture/VAD staging and playback held the same filesystem lock as network/CPU
  transcription. Capture backed up (VAD queue 100, raw queue 25) during local ASR.
  The old process accumulated 93 input overflow/status events before maintenance.
- Callback arrival time supplied recording timestamps, producing artificial time
  gaps when CPU scheduling delayed callbacks.
- Staging compressed audio as 12 kbps Opus before recognition; enhancement encoded
  it again. Per-clip loudness normalization raised background noise by roughly
  5–7 dB and did not remove the playback gaps. No full-scale ADC clipping was found
  in the five approved originals.
- Four conversations echoed the recognizer's old bilingual prompt. A new prompt-free
  Groq comparison of all five verified recordings produced zero occurrences of
  that prompt. This comparison did not overwrite historical journal entries.
  Other recognition errors remain; one diagnostic returned an unexpected language.
  Production's existing language review/retry policy remains active.

## Changes

Capture staging and playback cache writes now use separate locks, while explicit
clear-all acquires all three locks. Silero inference is serialized separately.
New staging is lossless 16-bit FLAC with WAV fallback; older Opus files still load.
PortAudio ADC timestamps determine sample time, with a larger 0.5-second hardware
buffer. True timing discontinuities split staging groups rather than being hidden
by concatenation. Local ASR/voice encoder computation uses one thread and the daemon
CPU allowance is 1.5 cores.

Minute-level Groq pacing now defers queued work instead of invoking local ASR.
Other safety budgets and fallback rules remain enforced. The old text prompt was
removed; historical prompt echoes are marked for review without rewriting source
transcripts or provider payloads.

The dashboard defaults to **Full recording** when retained parent sources exist.
This includes unverified voices in those source clips, which may extend beyond the
verified note. **Verified speech** remains available, with its original gaps.
Neither playback path changes ASR eligibility. Full playback does not reconstruct
missing input samples or promise a continuous archive of every excluded source.
Five-millisecond fades soften isolated playback cut edges; original files are
unchanged. Future enhanced clips use gentle denoising and fixed gain instead of
per-clip loudness normalization.

## Verification and limits

- 115 tests passed, 3 skipped; frontend lint and production build passed.
- Authenticated original/full HTTP 206 range playback passed for all five sampled
  IDs. Browser playback advanced for full and verified modes. Unauthenticated
  full playback returned 401.
- A 37.22-second real local ASR check ran while capture advanced 147 callbacks:
  zero overflows before/after, both capture queues zero afterward.
- A separate 45-second browser observation advanced 175 callbacks, zero overflows,
  live workers, unmuted external PCH microphone, no capture stall.
- Database quick_check returned ok; Shreyansh and Shivangi profiles stayed enabled.
- New FLAC files were observed on external storage after deployment.
- Direct human-like listening is unavailable in this Codex session. Audio was
  decoded, measured, played through the browser and re-transcribed, but was not
  independently heard or word-for-word verified. Missing historical samples and
  prior lossy compression cannot be undone.

Evidence on HP:
`/mnt/music-drive/voice-journal/voice-journal/voice-journal/validation/audio-audit-20261016/`
(`five.json`, `prompt-free-comparison.json`, `capture-under-local-load.json`,
source bundle). Local QA logs are `/tmp/vj-audiofix-{tests,build,browser,load}.log`.
