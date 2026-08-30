# CPU Usage Patterns

Understanding how the batch scheduler uses CPU.

## Idle Detection

The scheduler samples CPU usage every 30 seconds:

```python
cpu_percent = psutil.cpu_percent(interval=1.0)
```

If CPU is below `cpu_idle_threshold` (default 30%) for `min_idle_duration_seconds` (default 60s), a batch is started.

## During Batch Processing

### Primary Model (large-v3)

- CPU usage: ~80-100% during transcription
- RTF: ~2.0x on Intel i3
- Memory: ~3-4GB for model

### Fallback Model (distil-large-v3)

- CPU usage: ~80-100% during transcription
- RTF: ~1.0x on Intel i3
- Memory: ~2-3GB for model

## Daytime Pattern

```
Time  CPU%  Scheduler Action
─────────────────────────────────────────
09:00  20%   Detect idle
09:01  15%   Continue idle tracking
09:02  18%   Idle for 60s → Start batch
09:03  95%   Processing (large-v3)
09:04  95%   Processing continues
09:05   5%   Batch chunk complete
09:05  20%   Check: still idle? YES
09:06  95%   Start next chunk
...
09:15  90%   User returns (CPU spike)
09:16   5%   Batch chunk complete
09:16  85%   Check: still idle? NO
09:16   -    Back off, wait for next idle
```

## Overnight Pattern

```
Time  CPU%  Scheduler Action
─────────────────────────────────────────
22:00   -    Overnight window starts
22:00   -    Start batch (ignore CPU)
22:00  95%   Processing
22:05   5%   Batch complete
22:05   -    Loop immediately
22:05  95%   Next chunk
...
06:00   -    Overnight window ends
06:00   -    Revert to daytime behavior
```

## Why Not Self-Interrupt?

The scheduler does NOT check CPU **during** a batch run:
1. Once started, batch runs to completion
2. CPU check only gates START, not continuation
3. Prevents constant start/stop from own processing load

This is intentional: large-v3 will spike CPU, which would trigger the idle check to fail, causing self-interruption.

## Tuning CPU Threshold

If batches start too eagerly:
```yaml
scheduler:
  cpu_idle_threshold: 20.0  # Lower = more conservative
  min_idle_duration_seconds: 120  # Longer wait
```

If batches don't start when expected:
```yaml
scheduler:
  cpu_idle_threshold: 40.0  # Higher = more aggressive
  min_idle_duration_seconds: 30  # Shorter wait
```

## Monitoring

```bash
# Watch scheduler decisions
tail -f logs/voice_journal.log | grep "Scheduler"

# Check current CPU
python -c "import psutil; print(f'CPU: {psutil.cpu_percent(interval=5):.1f}%')"

# Check backlog
python status.py
```
