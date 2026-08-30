# Performance Expectations

## Model Selection Trade-offs

| Model | RTF (i3) | Accuracy | Memory | Recommendation |
|-------|----------|----------|--------|----------------|
| large-v3 | ~2.0x | Best | ~4GB | Default for accuracy |
| distil-large-v3 | ~1.0x | Good | ~3GB | Fallback for overflow |
| medium | ~1.5x | Better | ~2.5GB | Alternative |
| small | ~0.8x | Good | ~1.5GB | Real-time capable (not recommended) |

## Daily Processing Estimates

Assuming 4.5 hours of speech per day:

| Model | RTF | Processing Time | Overnight Fit? |
|-------|-----|-----------------|----------------|
| large-v3 | 2.0x | 9.0 hours | Partial (needs daytime) |
| distil-large-v3 | 1.0x | 4.5 hours | Yes + daytime available |

## Batch Chunk Sizing

### Daytime (Conservative)
- Chunk size: 0.5 hours audio
- Processing time: ~1 minute
- Purpose: Quick back-off if user returns

### Overnight (Aggressive)
- Chunk size: 2.0 hours audio
- Processing time: ~4 minutes
- Purpose: Maximum progress when user asleep

## Scheduler Timing

- Idle check interval: 30 seconds
- Minimum idle duration: 60 seconds
- Overnight window: 10 PM - 6 AM (8 hours)

## Resource Requirements

### Minimum
- CPU: Intel i3 (8th gen) or equivalent
- RAM: 8GB
- Storage: 8GB for models + audio cache

### Recommended
- CPU: Intel i5 or equivalent
- RAM: 16GB (allows other apps overnight)
- Storage: 16GB for headroom

## Measuring Real Performance

Run benchmark on YOUR hardware:

```bash
python benchmark_asr.py audio_sample.m4a
```

Output example:
```
large-v3:
  Average RTF: 2.15x

  With 4.5h daily speech volume:
    Expected processing time: 9.7h
    Can process overnight (8h window): NO - NEEDS FALLBACK

distil-large-v3:
  Average RTF: 1.12x

  With 4.5h daily speech volume:
    Expected processing time: 5.0h
    Can process overnight (8h window): YES
```

## Tuning Based on Performance

If RTF > 3.0:
- System will heavily use fallback model
- Consider smaller batch sizes
- May need extended daytime windows

If RTF < 1.5:
- Can process entirely overnight
- Consider larger overnight_batch_hours
- May not need fallback often
