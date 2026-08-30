# Accuracy Improvements in Batch Architecture

This document explains the accuracy improvements in the batch processing refactor.

## Problem Diagnosis

The original real-time pipeline had these issues:

1. **Segments transcribed before grouped**: VAD segments as short as 0.5 seconds were sent directly to Whisper. Short, isolated, near-silent fragments are exactly what makes Whisper hallucinate.

2. **No anti-hallucination settings**: No VAD filter on decode, no `condition_on_previous_text` handling, no confidence gating.

3. **Real-time constraint**: Small model, low beam size, prioritizing speed over accuracy.

4. **Fragile speaker ID**: Pitch-threshold method (F0 ± 2 std dev) cascaded errors into conversation tagging.

5. **No audio preprocessing**: Raw mic audio went straight to VAD/ASR.

## Solutions Implemented

### Fix 1: Decouple capture from processing

- Audio capture + VAD run near-real-time (lightweight)
- Everything else is deferred batch processing
- Removes real-time-factor constraint entirely

### Fix 2: Merge segments before transcription

**Critical fix**: Consecutive VAD segments separated by less than 2.5 seconds are merged into a single audio buffer.

Enforced minimum 5-second transcription unit:
- Don't send isolated sub-5-second clips to Whisper
- Either merge with neighbor or hold until enough audio accumulates

Conversation grouping (90-second gap logic) stays as separate, coarser grouping for note boundaries.

### Fix 3: Large-v3 model with anti-hallucination settings

```yaml
asr:
  model_size: "large-v3"
  compute_type: "int8"
  vad_filter: true                    # Trims silence before decoding
  condition_on_previous_text: false   # Prevents hallucination cascade
  beam_size: 5                        # Full beam for accuracy
  initial_prompt: "Shreyansh, Shivangi"  # Vocabulary biasing
```

### Fix 4: Confidence gating

Every segment gets confidence metrics:
- `no_speech_prob`: Probability of non-speech
- `avg_logprob`: Average log probability of tokens

Segments with low confidence are:
- Kept (not discarded)
- Flagged with ⚠️ marker in Obsidian
- `needs_review: true` in frontmatter

### Fix 5: Audio preprocessing

- Denoising via noisereduce before VAD and ASR
- Gain normalization for consistent loudness
- Reduces false VAD triggers on background noise

### Fix 6: Embedding-based speaker ID

Replaced pitch-threshold with speaker embeddings:
- Resemblyzer for lightweight CPU inference
- Cosine similarity matching against reference embeddings
- More robust to voice variation

### Fix 8: Idle-triggered scheduler with backlog safety

- Batch jobs run when CPU <30% for 60+ seconds
- Guaranteed overnight window (10 PM - 6 AM)
- Daytime: small chunks (0.5h) to back off if user returns
- Overnight: larger chunks (2h) for progress
- Adaptive fallback when backlog exceeds 24h

## Expected Quality Improvement

| Issue | Before | After |
|-------|--------|-------|
| Hallucination on silence | Common (repeated/looped phrases) | Rare (minimum 5s units prevent) |
| Uncertain segments | Silently trusted or discarded | Flagged with ⚠️ marker |
| Speaker misidentification | Frequent (pitch threshold fragile) | Rare (embeddings robust) |
| Model accuracy | Small model, low beam | Large-v3, full beam |
| Processing constraint | Keep up with real-time | Process when idle |

## Monitoring Quality

Check the confidence markers in Obsidian notes:
- `⚠️` after a transcript line = uncertain
- `needs_review: true` in frontmatter = note has uncertain segments

Run benchmark on your hardware:
```bash
python benchmark_asr.py sample_audio.m4a
```

Check backlog status:
```bash
python status.py
```
