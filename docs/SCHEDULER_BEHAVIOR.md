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
