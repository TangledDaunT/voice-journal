# Benchmarking Guide

## Quick Start

Run the benchmark script to measure actual RTF on your hardware:

```bash
python benchmark_asr.py /path/to/sample_audio.m4a
```

The script will:
1. Load the audio file
2. Run transcription with `large-v3` and `distil-large-v3`
3. Report RTF (processing time / audio duration)
4. Calculate expected daily processing time for your speech volume

## Understanding RTF

**Real-Time Factor** = Processing Time ÷ Audio Duration

| RTF | Meaning |
|-----|---------|
| < 1.0 | Faster than real-time (can process live) |
| ~2.0 | Large-v3 on i3 (typical) |
| > 5.0 | Very slow, consider smaller model |

## Example Output

```
BENCHMARK RESULTS SUMMARY
============================================================

large-v3:
  Average RTF: 2.15x
  Results: 4

  With 4.5h daily speech volume:
    Expected processing time: 9.7h
    Can process overnight (8h window): NO - NEEDS FALLBACK

distil-large-v3:
  Average RTF: 1.12x
  Results: 4

  With 4.5h daily speech volume:
    Expected processing time: 5.0h
    Can process overnight (8h window): YES
```

## Tuning Batch Sizes

Based on benchmark results, adjust in `config/default_config.yaml`:

```yaml
scheduler:
  daytime_batch_hours: 0.5   # Lower if RTF is high
  overnight_batch_hours: 2.0 # Higher if RTF is low
  backlog_overflow_hours: 24.0 # Adjust based on tolerance
```

## Troubleshooting

### "Out of memory" errors

Large models need RAM:
- `large-v3`: ~3GB RAM
- If OOM, try smaller `compute_type` or model

### Very slow RTF (>5x)

Check:
1. CPU thermal throttling
2. Background processes
3. Model downloaded correctly (onnx cache)

### CI/CD Integration

```bash
python benchmark_asr.py sample.m4a --output results.json
```

Parse JSON for automated checks.
