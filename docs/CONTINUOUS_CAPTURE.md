# Continuous capture and live listening

The previous live path ran stateless VAD on approximately six-second buffers.
Silero's 100 ms silence split and per-result padding produced many short clips;
LiveProcessor then saved every verified speaker span as its own conversation.
The 1–3 second cards were speech extraction spans, not evidence of one-second
hardware recordings. The old timestamp was also taken at callback completion;
it is now offset by the callback's sample duration.

The active daemon accumulates audio across capture buffers. It checks for a
pause after 12 seconds and flushes when there is at least 600 ms trailing silence.
Continuous speech is bounded to 24 seconds per ASR unit. Forced boundaries use a
low-energy 40 ms frame in the final two seconds, plus 500 ms of context on each
side. Context is subject to the same speaker gate as all other audio. Word
midpoints assign returned words to nonoverlapping sample cores. Missing word
timestamps produce a review marker, not an invented or duplicated transcript.
These rules improve boundary handling but do not guarantee ASR recognition.
The six-second capture polling interval and ASR/queue time add latency.

New units join the previous conversation on the same IST date if their gap is
at most 12 seconds and the conversation would remain at most 30 minutes long.
Speaker changes retain timed turns within the same conversation. Original
provider payloads and per-turn decisions remain in journal_segments. The schema
migration removes the former unique conversation_id constraint transactionally;
existing rows and historical IDs remain. Imported entries stay independent.
Playback assembles only saved, verified clips on their original timeline; skipped
speaker/media ranges become silence. It never fills a rejected gap with raw room
audio. Noise-reduced and original variants remain separately playable. A cache
version reflects the current conversation membership; reopen audio to hear newer
turns as a conversation grows. Older cache versions remain until clear-all.

Groq and faster-whisper accept a single language hint, not a two-language
allowlist. First pass uses automatic detection, transcription (not translation),
and a bilingual spelling prompt. Validation checks actual language and scripts
in text, segments, and words. Latin, Devanagari, punctuation, digits and symbols
are preserved. Unexpected language/script triggers one Hindi-guided retry;
persistently invalid output is shown as needing review, with both provider
responses retained internally. Local batch results follow the same validation.
Historical unexpected scripts are flagged in the dashboard without deleting or
rewriting historical transcripts. Latin-script output alone cannot establish
whether Hindi has been romanized; real mixed-speech acceptance remains necessary.

Official references checked 2026-10-16:
- https://console.groq.com/docs/speech-to-text
- https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py

The HP analog external microphone shares the Realtek ALC236 sound card with the
built-in mic. On inspection, ALSA Mic Jack was on and codec node 0x23 selected
node 0x19 (external analog jack), with internal node 0x12 muted in that mixer.
No USB microphone was present. Deployment pins the ALSA card identity PCH and
uses a named plug PCM for 16 kHz resampling. A named ALSA jack control is checked
before queue-thread delivery and in the health loop, including while muted. A
missing control/card/jack blocks capture delivery, without a default-device
fallback. The card has no individual external-mic serial number. Kernel jack
routing and disconnect/reconnect still require physical user acceptance.

Dashboard **Listen live** plays the HP microphone through Web Audio; it does not
request the browser device's microphone. It works while normal journaling is muted
without changing mute or enabling ASR. This is room audio before speaker filtering.
Only authenticated dashboard users can start listening or fetch PCM. A browser
renews an eight-second lease; Stop, page departure, or lease expiry stops delivery.
At most sixteen approximately 256 ms WAV parts (about four seconds) exist in a
bounded 1 MiB shared RAM buffer while listening; it is zeroed on stop or expiry.
Docker web shares the daemon IPC namespace. All persistent recordings and runtime
state remain on the external drive. The RAM handoff avoids exFAT metadata/fsync
stalls observed during the first live browser check.
No new capture device is opened. Slow clients skip to recent audio rather than
accumulating a growing delay. Multiple browser listeners share one room-listening
lease, so Stop from one also stops other listeners. Use headphones near the HP.

Acceptance requires real enrollment, then 30–60 seconds of Hindi, English and
mixed speech across chunks, natural pauses, speaker changes, and media rejection
with both people silent. Listen live also provides a direct audible check of
input selection. Synthetic tests establish sample/timestamp ownership, not word
accuracy or real-world speaker filtering accuracy.
