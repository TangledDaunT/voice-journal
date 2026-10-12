# Voice Journal Evaluation Harness

Phase 1 evaluation tooling for measuring WER/CER on Hinglish speech. Measurement only — does not modify daemon, web, or transcribe services.

## Directory Structure

```
eval/
├── record_gold.py        # Guided gold-set recording (48kHz FLAC + 16kHz WAV)
├── draft_transcribe.py   # faster-whisper large-v3 int8 draft transcripts
├── correct_ui.py         # Flask UI for correcting transcripts (port 5001)
├── normalize.py          # Text normalization (Devanagari→Roman, variants)
├── score.py              # Evaluation: WER, CER, RTF, repetition, hallucinations
├── scripts.yaml          # Scripted passages + scenario definitions
├── variants.yaml         # Spelling variant → canonical mapping
├── systems.yaml          # System definitions (model, audio variant, decode params)
├── requirements.txt      # Python deps (separate venv)
├── README.md             # This file
└── <tag>/                # Per-tag recording directory (created at runtime)
    ├── SCRIPTED_HI.flac
    ├── SCRIPTED_HI.wav
    ├── SCRIPTED_HI.draft.json
    ├── SCRIPTED_HI.ref.txt
    └── ...
results/                  # Evaluation outputs (created at runtime)
    ├── <tag>_<timestamp>.csv
    └── <tag>_<timestamp>.md
```

## Prerequisites

```bash
# 1. Create separate venv for evaluation (not the Docker venv)
cd /home/shreyansh/voice-journal
python3 -m venv eval-venv
source eval-venv/bin/activate
pip install -U pip
pip install -r eval/requirements.txt

# 2. Install ffmpeg (for resampling & audio variants)
sudo apt-get update && sudo apt-get install -y ffmpeg

# 3. Ensure models are downloaded (first run will download large-v3 int8 ~3GB)
#    Models cache in ~/.cache/huggingface/hub/
```

## Step-by-Step Run Order

### 0. Stop Daemon (Free Microphone)

```bash
./vj-control.sh stop
```

### 1. Record Gold Set

```bash
# First recording session (e.g., at desk)
source eval-venv/bin/activate
python eval/record_gold.py --tag desk

# Re-record with different mic (e.g., lav mic)
python eval/record_gold.py --tag lav

# Re-record specific scenarios only
python eval/record_gold.py --tag desk --only SPONT_SOLO SPONT_NOISY --force
```

**What happens:**
- 8 guided scenarios (3 scripted + 4 spontaneous + silence)
- Live level meter, clipping warning, SNR estimation
- Saves FLAC (48kHz, lossless) + WAV (16kHz) per scenario
- Output: `eval/desk/SCENARIO_ID.flac` + `.wav`

### 2. Restart Daemon

```bash
./vj-control.sh start
```

### 3. Draft Transcribe (SPONT_* only)

```bash
source eval-venv/bin/activate
python eval/draft_transcribe.py --tag desk

# Force re-transcribe
python eval/draft_transcribe.py --tag desk --force
```

**What happens:**
- Runs faster-whisper large-v3 int8 on 16kHz WAV
- Language pinned to "hi", tuned decode params
- Output: `eval/desk/SCENARIO_ID.draft.json` (segments with timestamps, logprobs)

### 4. Correct Transcripts (Web UI)

```bash
source eval-venv/bin/activate
python eval/correct_ui.py --tag desk --host 0.0.0.0 --port 5001
```

**Then open in browser:**
- Local: `http://localhost:5001`
- Tailscale/LAN: `http://<your-tailscale-ip>:5001`

**UI Features:**
- Splits each SPONT_* take into ~15s chunks at silence boundaries
- Audio player with loop, 0.75×/1×/1.25×/1.5× speed
- Editable textarea prefilled with draft text
- "Mark unintelligible" checkbox (excludes from scoring)
- Save progress per chunk, auto-advance
- Reference convention (displayed at top):
  - Roman-script Hinglish, lowercase
  - Punctuation not required
  - Numbers as words or digits
  - Devanagari auto-transliterated

**Output:** `eval/desk/SCENARIO_ID.ref.txt` (one line per chunk)

### 5. Score / Evaluate

```bash
source eval-venv/bin/activate
python eval/score.py --tag desk
```

**What happens:**
- Loads systems from `eval/systems.yaml` (3 baselines by default)
- Runs each system on each scenario's 16kHz WAV
- Normalizes both reference & hypothesis (same pipeline)
- Computes: WER, CER, Ins/Del/Sub, RTF, repetition loops, hallucinations
- Output: `eval/results/desk_<timestamp>.csv` + `.md`
- Prints summary table with best system per scenario highlighted 🏆

## Re-Recording Under New Tag

To compare mic setups, positions, or hardware:

```bash
# 1. Stop daemon
./vj-control.sh stop

# 2. Record with new tag
python eval/record_gold.py --tag lav

# 3. Restart daemon
./vj-control.sh start

# 4. Draft transcribe new tag
python eval/draft_transcribe.py --tag lav

# 5. Correct new tag
python eval/correct_ui.py --tag lav

# 6. Score new tag (or compare both)
python eval/score.py --tag lav
python eval/score.py --tag desk  # Re-score original for comparison
```

**Compare tags:** Open both markdown results side-by-side, or load CSVs into pandas.

## Adding New Systems

Edit `eval/systems.yaml` and add a new entry:

```yaml
systems:
  my_new_system:
    audio_variant: "raw16k"  # or ffmpeg filter like "afftdn=nr=10,highpass=f=80"
    model: "large-v3"
    compute_type: "int8"
    device: "cpu"
    language: "hi"
    beam_size: 5
    temperature: [0.0, 0.2, 0.4]
    compression_ratio_threshold: 2.4
    log_prob_threshold: -1.0
    no_speech_threshold: 0.6
    vad_filter: true
    condition_on_previous_text: false
    word_timestamps: true
    initial_prompt: "Shreyansh, Shivangi. Use only Hindi and English; do not output any other language."
```

Then re-run scoring:

```bash
python eval/score.py --tag desk --only-systems my_new_system
```

## CPU Performance Notes

- All transcription runs with `OMP_NUM_THREADS=2`, `cpu_threads=2` (faster-whisper)
- Use `nice -n 10` if system feels sluggish:
  ```bash
  nice -n 10 python eval/draft_transcribe.py --tag desk
  nice -n 10 python eval/score.py --tag desk
  ```
- Large-v3 int8 ~2-3× real-time on i3; large-v2 ~1.5-2×
- Draft transcription is one-time; scoring re-runs all systems

## Output Interpretation

| Metric | Good | Bad | Notes |
|--------|------|-----|-------|
| WER | <15% | >30% | Word Error Rate (primary) |
| CER | <10% | >20% | Character Error Rate |
| RTF | <1.0x | >3.0x | Real-Time Factor (processing/audio) |
| Repetitions | 0 | >2 | Pathological loops |
| Hallucinations (SILENCE) | 0 | >5 | Words on pure silence |

## Troubleshooting

**No audio device / permission denied:**
```bash
# Add user to audio group
sudo usermod -a -G audio $USER
# Log out/in or reboot
```

**ffmpeg not found:**
```bash
sudo apt-get install ffmpeg
```

**Model download fails:**
```bash
# Pre-download
python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8')"
```

**CUDA/GPU errors (should not happen):**
- Ensure `device: "cpu"` and `compute_type: "int8"` in systems.yaml
- Set `CUDA_VISIBLE_DEVICES=""` if needed

**Port 5001 in use:**
```bash
python eval/correct_ui.py --tag desk --port 5002
```

## File Locations (Not in Git)

- Audio: `eval/<tag>/` (FLAC + WAV)
- Drafts: `eval/<tag>/*.draft.json`
- References: `eval/<tag>/*.ref.txt`
- Results: `eval/results/*.csv`, `*.md`
- Add to `.gitignore`:
  ```
  eval/*/
  eval/results/
  eval-venv/
  ```

## Next Steps (Future Phases)

- Add denoising chains to `systems.yaml` (rnnoise, noisereduce, spectral gating)
- Add Hinglish-specialized fine-tuned models
- Add speaker-diarization-aware scoring
- Automate A/B comparison reports across tags