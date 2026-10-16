# Microphone studio and recovery — 2026-10-16

Open https://voice.tangleddaunt.dpdns.org/settings and use the existing dashboard login.
The user confirmed the existing domain spelling (“daunt”). The originally typed
“taunt” hostname has no DNS record and was not configured as a new domain.

## Listening and sound controls

- Select **HP journal microphone** for the real HP input, or **This computer’s
  microphone (Mac / PC)** for local browser monitoring. Use headphones.
- Local monitoring requires HTTPS, browser permission, and macOS permission for
  the browser/app under System Settings → Privacy & Security → Microphone.
  Permission requests can be cancelled. A request that remains pending for 25
  seconds shows actionable guidance; any stream granted after cancellation is stopped.
- The level meter shows the processed monitor signal. Stop releases local tracks,
  closes the audio context and expires/stops the HP listening lease.
- **HP capture level** and **HP microphone boost** use the actual ALSA Capture
  Volume and Mic Boost Volume controls on the configured PCH card. Apply changes
  explicitly. These affect new raw recordings and voice verification. No initial
  gain adjustment was made: current hardware was 100% capture, boost step 2/3.
- Mac hardware input gain remains in macOS Sound settings. Software gain and EQ
  in this dashboard process its browser monitor; they are not a system-wide Mac
  virtual microphone, and Mac audio is not uploaded or added to journal entries.
- Gain, output trim, low/high cuts, eight EQ bands (80, 160, 315, 630, 1250, 2500,
  5000, 7000 Hz), compressor threshold/ratio/attack/release, limiter, and Flat,
  Speech, Warm, Clarity presets are available. Live changes preview immediately.
- Save sound settings to apply them to subsequent live-monitor sessions and newly
  generated enhanced HP recordings. Noise reduction (0–12 dB) applies only to
  enhanced recordings. Existing enhanced caches are not regenerated automatically.
- Original files and ASR/speaker-verification input are preserved. Software monitor
  processing does not bypass enrollment or rewrite recorded originals. There is
  no noise gate that cuts quiet words.

Sound preferences are validated server-side and written atomically to
`DATA_ROOT/voice-journal/settings/microphone.json` on the external disk.
Profiles reject unknown fields, non-finite values, incorrect EQ lengths, and
out-of-range levels. Hardware control names and the input card are fixed by the
server configuration. Hardware PUT validates every requested level before writing.

## Failure and repair

The kernel logged a USB disconnect at 02:58:34 IST. The external drive returned as
/dev/sdc1 instead of /dev/sdb1; its stable UUID remains 6EFF-790D. Docker's original
bind mounts retained broken storage references. The daemon restarted with
“unable to open database file”; the web service had EIO reading runtime status.

The known external drive was mounted again and journal containers recreated.
SQLite quick_check returned ok and both real enrolled profiles remained enabled.
The kernel reported an unclean exFAT unmount; no destructive filesystem repair or
formatting was performed. Physical USB/cable failures cannot be prevented by the
application. USB autosuspend was already disabled for this device (power/control=on).

`voice-journal-recover.timer` checks every 30 seconds. Its root-owned helper stops
only the journal services when the known drive is absent, mounts the configured
UUID on reconnection, validates the existing DB header, and recreates the journal
containers against the restored mount. It also handles sustained unhealthy
containers after three checks. It never creates a replacement database on the
internal disk or formats a drive. An unreadable/corrupted filesystem still needs
attention. `/run/voice-journal-maintenance` suppresses recovery during maintenance.
`/etc/voice-journal-release` identifies the active release.

## Public proxy

The app web service now persistently joins external Docker network nginx-proxy-net.
Nginx uses Docker DNS to resolve voice_journal_web dynamically across recreations.
The existing Cloudflare Tunnel terminates TLS and forwards this hostname to Nginx;
no additional tunnel credentials or DNS records were needed. Basic Auth remains
required on dashboard/audio/settings routes.

The previous generic API rate limit was only 10 requests/second; live audio polling
can exceed this. The microphone location now allows 50 requests/second with burst
80, disables buffering/cache, and retains no-store responses. SSE also bypasses
buffering. See deploy/voice-journal.nginx.conf.

Nginx reload was additionally blocked by the stopped Immich service's static DNS
lookup. That existing upstream was changed to dynamic Docker DNS with the same
target and behavior. Other service targets were preserved. Old Nginx configurations
are backed up in the previous audiofix release directory.

## Verification

- 128 tests passed, 3 skipped; frontend lint and build passed.
- Actual public HTTPS HP listening delivered audio, measured around -25 to -26
  dBFS in Chrome. An 80 Hz EQ change reached +6 dB in the active audio graph.
- Settings saved/read back; hardware writes at their existing values verified
  native control access; invalid requests returned 400. Original levels/preferences
  were restored after checks. Anonymous settings access returned 401.
- Local Mac/PC monitor, track cleanup and cancellation were exercised using an
  injected synthetic browser MediaStream. The native getUserMedia request remained
  pending in the automated Mac Chrome process even with browser permission granted;
  physical Mac microphone capture is not independently confirmed. The real user's
  browser and macOS microphone permissions must allow capture.
- Capture at final browser check: 1,157 callbacks, zero input overflows, both queues
  empty, both consumers alive, external PCH input active, journal unmuted.
- Deployed FFmpeg enhancement filter executed successfully in the daemon image.
- Recovery timer is enabled/active; its no-op healthy check passed. Unit coverage
  simulates drive loss/reconnection without physically interrupting production USB.
- Desktop/mobile screenshots checked. Audio perception is unavailable in this
  agent session; stream/graph/meter checks are not an independent listening review.

Local evidence: /tmp/vj-studio-tests.log, /tmp/vj-studio-build.log,
/tmp/vj-studio-browser.log, /tmp/vj-mac-diagnostic.log and screenshots.
