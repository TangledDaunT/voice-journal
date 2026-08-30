# Backlog Monitoring Guidelines

## What is Backlog?

Backlog is the total hours of audio queued but not yet processed. It represents work waiting to be transcribed.

## Monitoring Metrics

### Current Backlog Hours
Total hours of audio in the queue.

```bash
python status.py | grep "Total queued"
```

### Growth Rate
Whether backlog is growing or shrinking day-over-day.

```bash
python status.py | grep "growth_warning"
```

### Overflow Status
Whether system is using fallback model (backlog > 24h).

```bash
python status.py | grep "overflow"
```

## Alerting Thresholds

| Condition | Severity | Action |
|-----------|----------|--------|
| Backlog > 48 hours | CRITICAL | Investigate immediately, manual processing |
| Backlog > 24 hours | WARNING | Monitor closely, consider manual batch |
| Backlog growing | WARNING | Check RTF, adjust settings |
| Scheduler stopped | WARNING | Restart daemon |

## Automatic Handling

The system auto-scales when backlog grows:

1. **Normal (< 24h)**: Use `large-v3` primary model
2. **Overflow (> 24h)**: Auto-switch to `distil-large-v3` fallback
3. **Continuous**: Overnight window processes regardless of CPU

## Manual Intervention

### Clear backlog manually

```bash
# Run batch immediately
python -m processing.batch_processor

# Use faster fallback
python -m processing.batch_processor --fallback
```

### Adjust thresholds

In `config/default_config.yaml`:

```yaml
scheduler:
  backlog_overflow_hours: 24.0  # Lower for faster fallback
```

## Health Check Integration

For monitoring systems (Nagios, Prometheus):

```bash
./scripts/health_check.sh
```

Returns:
- Exit 0: OK
- Exit 1: WARNING
- Exit 2: CRITICAL
