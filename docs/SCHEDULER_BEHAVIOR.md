# Scheduler Behavior Reference

## Decision Flow

The scheduler decides when to run batch processing based on:

```
┌─────────────────────────────────────────────────────────────┐
│                    SCHEDULER CHECK (every 30s)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Already running?│──YES──▶ Return (skip)
                    └─────────────────┘
                              │NO
                              ▼
                    ┌─────────────────┐
                    │ In overnight    │
                    │ window?         │──YES──▶ Run batch (2h chunk)
                    │ (10PM-6AM)      │              │
                    └─────────────────┘              │
                              │NO                     │
                              ▼                       │
                    ┌─────────────────┐              │
                    │ CPU < 30%       │──NO──▶ Return (wait)
                    │ for 60+ sec?    │              │
                    └─────────────────┘              │
                              │YES                   │
                              ▼                       │
                    Run batch (0.5h chunk)◀──────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Backlog > 24h?  │──YES──▶ Use fallback model
                    └─────────────────┘
                              │NO
                              ▼
                    Use primary model
```

## Daytime Behavior (6 AM - 10 PM)

- **Idle detection**: CPU must be < 30% for at least 60 seconds
- **Batch size**: 0.5 hours of audio (30 min)
- **Re-check**: After each chunk, scheduler re-evaluates idle
- **Back-off**: If you return to laptop, next idle check fails and scheduler stops

Example timeline:
```
09:00  You leave laptop
09:01  CPU drops below 30%
09:02  Idle detected, batch starts (30 min audio = ~1 min processing)
09:03  Batch chunk completes
09:03  Scheduler checks: still idle? YES
09:03  Next chunk starts
...
09:15  You return, CPU spikes
09:16  Batch chunk completes
09:16  Scheduler checks: still idle? NO
09:16  Backs off, processes no more
```

## Overnight Behavior (10 PM - 6 AM)

- **No idle check**: Runs regardless of CPU
- **Batch size**: 2.0 hours of audio
- **Continuous**: Loops immediately after each chunk
- **Full-CPU acceptable**: You're assumed asleep

Example timeline:
```
22:00  Overnight window starts
22:00  Batch starts (2h audio = ~4 min processing)
22:04  Batch chunk completes
22:04  Scheduler checks: in window? YES
22:04  Next chunk starts immediately
...
06:00  Overnight window ends
06:00  Revert to daytime behavior (idle-gated)
```

## Backlog Overflow

When backlog exceeds 24 hours:
- Automatically switches to `distil-large-v3`
- Continues until backlog drops below threshold
- Logged clearly: "Starting batch: ... fallback=True"

## Configuration

Key settings in `config/default_config.yaml`:

```yaml
scheduler:
  cpu_idle_threshold: 30.0           # CPU % below this = idle
  min_idle_duration_seconds: 60      # Must be idle for this long
  idle_check_interval: 30            # How often scheduler checks

  guaranteed_window_start_hour: 22   # 10 PM
  guaranteed_window_end_hour: 6      # 6 AM

  daytime_batch_hours: 0.5           # 30 min audio per chunk
  overnight_batch_hours: 2.0         # 2h audio per chunk

  backlog_overflow_hours: 24.0       # Switch to fallback above this
```

## Monitoring

Check current state:
```bash
python status.py
```

Output includes:
- `scheduler_running`: True/False
- `currently_processing`: True/False
- `backlog_hours`: Current depth
- `in_guaranteed_window`: True/False
- `cpu_idle`: True/False
- `is_overflow`: True/False (using fallback?)

## Important Note

The scheduler does NOT self-interrupt. Once a batch chunk starts:
- It runs to completion
- Scheduler loop is blocked during processing
- Idle is only checked BETWEEN chunks, not during

This prevents constant start/stop from its own CPU usage.

## Stabilization note (2026-10-15)

The CPU/Groq router and battery guard requested in the upgrade are not implemented
in this pass. The current YAML has `process_all_day: true`, so the original idle
flow above does not describe the deployed default accurately. No realtime factor
in the illustrative examples above was measured by this audit.

The batch path now retains staged source files until a conversation commit succeeds,
including on low-energy or empty ASR results. Such units remain queued for now;
a durable rejected-silence status is still needed. Trailing conversations flush at
each batch boundary so acknowledgement does not depend on in-memory grouping.
This can split a conversation between batches. A SHA-256-derived 48-bit identifier
makes retries of the same source group stable; replay with changed grouping can
still create duplicate text. Durable per-segment idempotency remains outstanding.

## Later Groq-first deployment (2026-10-15)

The active daemon now uses `processing.live_pipeline.LiveProcessor`, which checks
the durable staging queue every second. Speech is detected from roughly six-second
capture buffers. Cloud units do not wait for the legacy overnight/idle scheduler.
Groq is primary on AC and battery; local fallback runs only on AC. The legacy
BatchScheduler remains for manual/legacy use, and its earlier descriptions above
must not be interpreted as the current daemon's routing behavior. A queue count
of zero is normal after completed clips have been saved or while no speech is
being detected. Capture signal and last successful save are separate live metrics.


## Enrolled-voice gate (2026-10-15)

The live worker and manual batch entry points verify enabled speaker profiles
before either ASR engine. No profiles leaves staging pending with
`enrollment_required`; explicit calibration takes priority. Unknown source audio
is retained locally with a decision ledger and never sent to ASR. Accepted ranges
keep original time offsets; a partial failure keeps the parent queued and child
IDs make retries idempotent. Groq-first/battery and local-fallback rules above
still apply after verification. See DEPLOYMENT_STATUS.md for exact thresholds.
