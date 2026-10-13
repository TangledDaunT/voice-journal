# Handoff: Voice Journal — Remote SSH Setup & HTTPS/Audio Fixes

**Date:** 2026-10-13
**Purpose:** Full context transfer to another agent. Everything below is historical state plus the exact point where work stopped.

---

## 0. STATUS: ALL PRIORITY TASKS COMPLETED (2026-10-13 ~16:35 IST)

Sections §4–§6 below are **HISTORICAL** — do not follow their plans. Current verified state:

### ✅ HTTPS / Error A — FIXED
- **Do NOT bind Flask to port 443.** 443 is owned by `tailscaled` (`100.99.161.57:443`, Tailscale serve) and the unrelated `nginx-proxy` container (`192.168.1.6:443`, `0.0.0.0:80`). The §5 plan (Flask `--ssl` on 443) is unworkable without killing unrelated services and was **abandoned**.
- **Fix applied:** restored `ports: ["5000:5000"]` on the web service (the compose file had lost it entirely — nothing listened on host 5000) and reused the **already-configured Tailscale serve** (`/` → `http://127.0.0.1:5000`).
- **User URL: `https://shreyansh-hp-laptop-15-da0xxx.tail6e6a7a.ts.net`** — valid Let's Encrypt cert (no warning), secure origin, `getUserMedia` allowed. Verified `curl -s https://…ts.net/api/health` → 200 (strict TLS).
- `https://100.99.161.57` does **not** work (tailscaled needs SNI; browsers omit SNI for IPs). `http://100.99.161.57:5000` works but has no mic access.
- Flask runs plain HTTP on 5000. The `--ssl/--cert/--key` args in `web/app.py` are unused. `tls/` and `https_proxy.py` are obsolete (safe to delete).

### ✅ Error B (`sysdefault`) — FIXED
- **Root cause:** the daemon owns the mic through an ALSA **dsnoop** instance inside its container's *private* IPC namespace. The web container had its own IPC ns, could never join that instance → `sysdefault`/`default` never appeared in `sd.query_devices()` → sounddevice's `ValueError: No input device matching 'sysdefault'` escaped the `except sd.PortAudioError` fallbacks and reached the UI.
- **Fixes applied:**
  1. compose: `ipc: shareable` on **daemon**, `ipc: "service:daemon"` on **web** (web now joins daemon's IPC ns).
  2. Whisper cache copied to `./hf_cache` (464 MB) and mounted at `/root/.cache/huggingface` on the daemon — recreates load the model in ~5 s instead of re-downloading (2–3 min).
  3. `web/app.py`: 8× `except sd.PortAudioError:` → `except (sd.PortAudioError, ValueError):` (backup at remote `/tmp/app.py.bak`; the `except sd.PortAudioError as e:` at line ~1370 intentionally untouched). `py_compile` OK.
- **Verified:** web container now enumerates `sysdefault (128 in)` + `default`; concurrent `sd.rec` returns real levels **while** the daemon captures; `POST /api/calibration/test_levels` → `{success:true, quality:"acceptable"}`; `POST /api/audio/record_test` → `{success:true, url:…}`.

### ✅ Infrastructure facts to remember
- `web/app.py` is now **bind-mounted** (`./web/app.py:/app/web/app.py:ro`) — container recreates keep all patches. To change it: edit the repo file, then `docker restart voice_journal_web`.
- `docker compose up` output sometimes truncates over the flaky SSH/expect session — redirect to a file on the remote and `scp` it back (worked reliably).
- Expected state: `voice_journal_web` Up+healthy on `0.0.0.0:5000`; `voice_journal_daemon` Up with `ipc=shareable` + hf_cache mount.
- End-to-end: daemon recreated 16:28, stream started 16000 Hz, VAD segments + ASR lines after restart, `daily_journals['2026-10-13']` has 546 segments (updated 16:28). `conversations` table = 0 rows (grouping is async — same as before, not a regression).

### Remaining OPTIONAL items
- External mic: none plugged (only internal ALC236). Re-check `cat /proc/asound/cards` / device list after plugging one in.
- Whisper `small` int8 at distance gives approximate transcripts (and silence-hallucinations like "You"/"Thank you") — consider `large-v3`.
- Live speak-and-verify spot test with the user.
- Optional cleanup: delete `tls/`, `https_proxy.py`, `/tmp/update_compose.py` (443 approach abandoned).

---

---

## 1. Objective

SSH into the user's Linux laptop (over Tailscale) and make the Voice Journal app's voice channel fully work:

- Mic detection (internal + external mics)
- Audio pickup and end-to-end transcription appearing in the web app
- Fix "Error querying device -1" on the calibration page
- Fix browser recording errors (see §6, unresolved items)

## 2. Environment / Access

- **Laptop hostname:** `shreyansh-hp-laptop-15-da0xxx`
- **Tailscale IP:** `100.99.161.57` (re-verify with `tailscale status` if unreachable)
- **SSH user:** `shreyansh`, **password:** `38000`
- **Remote project dir:** `/home/shreyansh/voice-journal/`
- **Containers:**
  - `voice_journal_daemon` — audio capture + ASR pipeline (`python daemon.py`)
  - `voice_journal_web` — Flask dashboard, currently HTTP on container port **5000**
- **DB:** `/data/voice-journal/db/voice_journal.db` (inside daemon container)

### SSH/quoting pitfalls (IMPORTANT)

- `sshpass` is **not available locally** — must use `expect`:
  ```sh
  expect -c '
  spawn ssh -o StrictHostKeyChecking=no shreyansh@100.99.161.57 "COMMAND"
  expect {
      "password:" { send "38000\r"; exp_continue }
      eof
  }
  '
  ```
- Quoting inside `expect -c '...'` is fragile. **Avoid nested `\"` and heredocs** — they break the Tcl parser (caused multiple `invalid command name` failures).
- **Preferred pattern:** write scripts locally with the `write` tool, `scp` them to the remote, then run via `python3 /path/script.py`. Don't try to inline complex commands.
- Docker image rebuilds are **very slow** (huge build context). Prefer `docker cp <file> <container>:<path>` + `docker restart/stop/start` over `docker compose up -d --build`.
- Whisper model re-downloads to container cache on daemon restart (HF `Systran/faster-whisper-small`); daemon takes ~2–3 min to initialize.

## 3. Completed Fixes (verified working)

| Issue | Fix | Verification |
|---|---|---|
| "Error querying device -1" | Rewrote calibration endpoints in `web/app.py` with fallback (try alternate input device → `sysdefault` → return `device_in_use`) | `calibration/status` returns `current_input_device: "hw:0,0 (ALC236 Analog)"` |
| Audio "input overflow" | Sample-rate mismatch fixed: env vars renamed to `VJ_*` prefix; config set to 16000Hz (yaml had 48000 vs compose 16000) | Daemon runs clean, no overflow |
| Web container missing `/dev/snd` | Added `/dev/snd` device mapping + `group_add: audio` to `web` service | Device list works (with fallback) |
| `wave.Error` in `_append_wav` | `storage/daily_journal.py::_append_wav` changed from `wave.open(path, "ab")` to read frames with `"rb"` and rewrite with `"wb"` | Fix verified in container; daemon restarted 13:07:37 |
| End-to-end transcription | — | ASR logs show transcripts; DB has `daily_journals` row for `2026-10-13` (`[02:33:41] (en) Oh`) |

### Known-good state details

- Daemon env: `VJ_AUDIO_SAMPLE_RATE=16000`, `VJ_AUDIO_CHANNELS=1`, `VJ_AUDIO_BLOCK_SIZE=2048`
- `web/app.py` (both local copy and inside container) has been patched with CLI args:
  ```python
  parser.add_argument('--ssl', action='store_true', help='Enable HTTPS')
  parser.add_argument('--cert', default=None)
  parser.add_argument('--key', default=None)
  ...
  ssl_context = None
  if args.ssl:
      cert_file = args.cert or "/app/tls/cert.pem"
      key_file = args.key or "/app/tls/key.pem"
      ssl_context = (cert_file, key_file)
  app.run(host=args.host, port=args.port, debug=args.debug, ssl_context=ssl_context)
  ```
  Verified present in container at `/app/web/app.py` (grep hits at lines 1624/1628/1633).

## 4. The Two User-Reported Errors (BROKEN / IN PROGRESS)

### Error A — `Failed to start recording: Cannot read properties of undefined (reading 'getUserMedia')`

- **Root cause:** Browser blocks `getUserMedia` on insecure origins. Dashboard is served over plain HTTP.
- **Why it's needed:** The user is accessing `http://100.99.161.57:5000`.
- **Planned fix:** Serve dashboard over HTTPS (self-signed cert), then user visits `https://100.99.161.57` (accept cert warning).

### Error B — `Recording failed: No input device matching 'sysdefault'`

- **Root cause:** The web container's ALSA only enumerates HDMI outputs (0 input channels) because the **daemon holds the capture stream exclusively**. `sd.query_devices()` in the web container returns only:
  ```
  0 HDA Intel PCH: HDMI 0 (hw:0,3), ALSA (0 in, 8 out)
  1 HDA Intel PCH: HDMI 1 (hw:0,7), ALSA (0 in, 8 out)
  2 HDA Intel PCH: HDMI 2 (hw:0,8), ALSA (0 in, 8 out)
  3 hdmi, ALSA (0 in, 8 out)
  ```
- **Attempted fixes that FAILED (do not repeat):**
  - Writing a naive `/etc/asound.conf` with `pcm.sysdefault { type hw card 0 }` → **broke PortAudio entirely** (`PaErrorCode -9999`). Removing the file restored it. Do NOT write a bare `/etc/asound.conf` again without testing `sd.query_devices()` afterward.
  - `pcm.!default { type hw card 0 device 0 }` → did not add any input devices to the enumeration.
- **Viable approaches not yet completed:**
  - Configure ALSA `dsnoop` plugin properly (share capture device) inside the web container — attempted but not verified.
  - Bypass enumeration: make calibration/record endpoints use `hw:0,0` directly instead of searching `sysdefault`.
  - Or have the daemon expose a recording API so the web container never touches ALSA.
- **Note:** `calibration/test_levels` may return `device_in_use` or fail on `sysdefault` — known secondary issue; the daemon's own capture works fine.

## 5. HTTPS Setup — Current Exact State (work stopped here)

Artifacts created:

- **Self-signed cert:** `/home/shreyansh/voice-journal/tls/{cert.pem,key.pem}` (CN=100.99.161.57, 365 days) — created successfully on remote.
- **`/home/shreyansh/voice-journal/https_proxy.py`** — a standalone Python reverse proxy (port 443 → localhost:5000). It was started once, then **died** and later explicitly `pkill`-ed. **It is dead; do not rely on it.** (Log file `tls/proxy.log` empty.)
- **Local copies (on the agent machine):**
  - `/private/var/folders/1f/zwvfzdp97pj05zsgy_6kbrs80000gn/T/opencode/https_proxy.py`
  - `.../T/opencode/web_app_original.py` — **patched** `web/app.py` with `--ssl/--cert/--key` (scp'd to remote `web/app.py`, also `docker cp`'d into container)
  - `.../T/opencode/docker-compose-fixed.yml` — compose with TLS mount + SSL command
  - `.../T/opencode/update_compose.py` — Python script that rewrites remote `docker-compose.yml` with:
    - `./tls:/app/tls:ro` volume
    - command `["python","web/app.py","--host","0.0.0.0","--port","443","--ssl","--cert","/app/tls/cert.pem","--key","/app/tls/key.pem"]`
    - `ports: ["443:443"]`, healthcheck `curl -kf https://localhost:443/api/health`

### What actually happened / current remote state

1. An early heredoc attempt to overwrite remote `docker-compose.yml` **failed** (expect quoting error) — so the remote compose file **may still be the old version** (verify: `cat /home/shreyansh/voice-journal/docker-compose.yml`).
2. `docker inspect voice_journal_web --format "{{json .Config.Cmd}}"` returned:
   ```json
   ["python","web/app.py","--host","0.0.0.0","--port","5000"]
   ```
   → the container is **NOT** running with `--ssl`. Logs confirm: `Running on http://127.0.0.1:5000`.
3. Container `voice_journal_web` is **Up and healthy on HTTP 5000** (dashboard works, but no mic access in browser).
4. **Last action before handoff:** `scp`'d `update_compose.py` to `shreyansh@100.99.161.57:/tmp/update_compose.py` (scp reported success, 1853 bytes), but running it failed:
   ```
   python3: can't open file '/tmp/update_compose.py': [Errno 2] No such file or directory
   ```
   → **First task:** figure out where the file actually landed (possible quoting issue meant scp wrote elsewhere, or /tmp cleanup) — re-scp and verify with `ls -la /tmp/update_compose.py` immediately after transfer, or scp to `/home/shreyansh/voice-journal/update_compose.py` instead.

### Other HTTPS pitfalls encountered

- **Port 443 conflicts:** Something else on the host binds 443 on IPs `192.168.1.6` and the Tailscale IP (likely a Tailscale serve/funnel or existing service — `ss -tlnp` showed listeners on `100.99.161.57:443`, `192.168.1.6:443`, plus `:8443` and IPv6 equivalents). A `docker start` failed with `Bind for 192.168.1.6:443 failed: port is already allocated`. Clear/check before binding: `sudo lsof -ti:443 | xargs sudo kill -9` (was done at least once).
- One test run produced `ERR_SSL_PROTOCOL_ERROR` in the browser — consistent with two servers fighting over 443 (the dead Python proxy vs Flask).
- `curl -sk https://localhost:443/api/health` returned empty multiple times → not serving.
- Healthcheck in compose uses `curl -kf ...` — **verify curl exists in the web image** before relying on it.

## 6. Remaining Tasks (in priority order)

1. **Get the remote `docker-compose.yml` updated with SSL config** (run `update_compose.py`, after fixing the missing-file issue — see §5).
2. **Recreate the web container** so Cmd includes `--ssl` on port 443, with `./tls` mounted:
   - Ensure port 443 on host is free (kill conflicting listeners).
   - `cd /home/shreyansh/voice-journal && docker compose up -d --force-recreate web` (no `--build` needed if image unchanged — but note earlier "recreate" reused the OLD image; the patched `app.py` must be `docker cp`'d in again after any recreate, OR just `docker cp` app.py + `docker start` with an overridden command).
   - Verify: `docker inspect voice_journal_web --format "{{json .Config.Cmd}}"` shows `--ssl`, and `curl -sk https://localhost:443/api/health` returns 200.
3. **Tell user to visit `https://100.99.161.57`** (accept self-signed cert warning) — fixes `getUserMedia` error.
4. **Fix Error B (`sysdefault`)** — see §4 viable approaches. Recommended: bypass `sysdefault` in the record/calibration endpoints and use `hw:0,0` directly (or route recording through the daemon).
5. **Optional:** external mic — none detected (no USB audio devices; only internal ALC236 Analog). Re-check after user plugs one in: `arecord -l` / `cat /proc/asound/cards`.
6. **Optional accuracy:** Whisper `small` int8 at 1m distance gives approximate transcripts; user may want `large-v3`.
7. Verify live end-to-end: speak → check `docker logs voice_journal_daemon --since 13:07:37` for fresh ASR/VAD lines → query newest `daily_journals`/`conversations` rows → confirm what's transcribed vs. what was said.

## 7. Verification Commands Cheat-Sheet

```sh
# Status
docker ps | grep voice
docker logs voice_journal_web --tail 30
docker logs voice_journal_daemon --since 2026-10-13T13:07:37

# HTTPS check
curl -sk https://localhost:443/api/health

# Container cmd check
docker inspect voice_journal_web --format "{{json .Config.Cmd}}"

# Audio devices
docker exec voice_journal_web python3 -c "import sounddevice as sd; print(sd.query_devices())"
docker exec voice_journal_daemon sh -c "arecord -l"

# DB queries (inside daemon container)
docker exec voice_journal_daemon python3 -c "
import sqlite3
c = sqlite3.connect('/data/voice-journal/db/voice_journal.db')
print(c.execute('SELECT * FROM daily_journals ORDER BY id DESC LIMIT 5').fetchall())
"

# Port conflicts
ss -tlnp | grep 443
```

## 8. Relevant Files

| Path (remote) | Notes |
|---|---|
| `/home/shreyansh/voice-journal/docker-compose.yml` | Current: web `ports: 5000:5000` + bind-mounts `./web/app.py`; daemon `ipc: shareable` + `./hf_cache:/root/.cache/huggingface`; web `ipc: "service:daemon"`. NO 443/ssl (abandoned, see §0) |
| `/home/shreyansh/voice-journal/web/app.py` | Patched: calibration fallbacks + `ValueError` hardening (8×) + unused `--ssl/--cert/--key` args; bind-mounted read-only into container (md5 `41971db238d8bd6a6b266e6f5fe3832b`) |
| `/home/shreyansh/voice-journal/tls/{cert.pem,key.pem}` | Self-signed cert (exists, verified created) |
| `/home/shreyansh/voice-journal/https_proxy.py` | Dead standalone proxy — ignore/kill |
| `/home/shreyansh/voice-journal/storage/daily_journal.py` | `_append_wav` wave fix |
| `/home/shreyansh/voice-journal/config/default_config.yaml` | 16000Hz audio config |
| `/home/shreyansh/voice-journal/daemon.py`, `audio_capture/capture.py`, `config/settings.py` | Daemon pipeline |
| `/tmp/update_compose.py` | scp reported success but file "not found" when run — re-transfer to a safe path |

Local fixed copies: `/private/var/folders/1f/zwvfzdp97pj05zsgy_6kbrs80000gn/T/opencode/{web_app_original.py, docker-compose-fixed.yml, update_compose.py, https_proxy.py, default_config-fixed.yaml}`

## 9. Immediate Next Move

**All priority tasks are done — see §0.** Optional follow-ups are listed at the end of §0. Do not re-run `update_compose.py` (443 approach abandoned).
