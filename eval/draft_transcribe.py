#!/usr/bin/env python3
"""
eval/draft_transcribe.py

Run faster-whisper large-v3 int8 (CPU) on 16kHz WAV copies of SPONT_* takes.
Language pinned to "hi", specific decoding params for Hinglish.
Writes eval/<tag>/<take>.draft.json with segments.
"""

import argparse
import sys
import json
import time
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Limit threads for CPU-only i3
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import numpy as np
from faster_whisper import WhisperModel
from tqdm import tqdm


# ============================
# Decoding Configuration (from requirements)
# ============================
DECODE_CONFIG = {
    "model_size": "large-v3",
    "compute_type": "int8",
    "device": "cpu",
    "language": "hi",  # Pinned to Hindi for Hinglish
    "beam_size": 5,
    "temperature": [0.0, 0.2, 0.4],
    "compression_ratio_threshold": 2.4,
    "log_prob_threshold": -1.0,
    "no_speech_threshold": 0.6,
    "vad_filter": True,
    "condition_on_previous_text": False,
    "word_timestamps": True,
    "initial_prompt": "Shreyansh, Shivangi. Use only Hindi and English; do not output any other language.",
}


SPONT_SCENARIOS = [
    "SPONT_SOLO",
    "SPONT_CONVO",
    "SPONT_QUIET_FAR",
    "SPONT_NOISY",
]


def find_tag_dir(tag: str) -> Path:
    """Find the tag directory under eval/."""
    eval_dir = Path(__file__).parent
    tag_dir = eval_dir / tag
    if not tag_dir.exists():
        raise FileNotFoundError(f"Tag directory not found: {tag_dir}")
    return tag_dir


def load_audio_16k(wav_path: Path) -> np.ndarray:
    """Load 16kHz WAV as float32 mono."""
    import soundfile as sf
    audio, sr = sf.read(wav_path, dtype='float32')
    if sr != 16000:
        raise ValueError(f"Expected 16kHz, got {sr}Hz")
    if audio.ndim == 2:
        audio = audio[:, 0]  # Mono
    return audio


def transcribe_audio(model: WhisperModel, audio: np.ndarray) -> List[Dict[str, Any]]:
    """Transcribe audio with configured parameters."""
    segments_gen, info = model.transcribe(
        audio,
        language=DECODE_CONFIG["language"],
        beam_size=DECODE_CONFIG["beam_size"],
        temperature=DECODE_CONFIG["temperature"],
        compression_ratio_threshold=DECODE_CONFIG["compression_ratio_threshold"],
        log_prob_threshold=DECODE_CONFIG["log_prob_threshold"],
        no_speech_threshold=DECODE_CONFIG["no_speech_threshold"],
        vad_filter=DECODE_CONFIG["vad_filter"],
        condition_on_previous_text=DECODE_CONFIG["condition_on_previous_text"],
        word_timestamps=DECODE_CONFIG["word_timestamps"],
        initial_prompt=DECODE_CONFIG["initial_prompt"],
    )

    segments = []
    for seg in segments_gen:
        segment_data = {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
            "avg_logprob": seg.avg_logprob,
            "no_speech_prob": seg.no_speech_prob,
            "compression_ratio": seg.compression_ratio,
        }

        if DECODE_CONFIG["word_timestamps"] and seg.words:
            segment_data["words"] = [
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability
                }
                for w in seg.words
            ]

        segments.append(segment_data)

    return segments


def main():
    parser = argparse.ArgumentParser(
        description="Draft transcribe SPONT_* scenarios using faster-whisper large-v3 int8",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval/draft_transcribe.py --tag desk
  python eval/draft_transcribe.py --tag lav --force
        """
    )
    parser.add_argument('--tag', required=True, help="Tag for the recording session (e.g., desk, lav)")
    parser.add_argument('--force', action='store_true', help="Re-transcribe even if draft exists")
    parser.add_argument('--model', default=DECODE_CONFIG["model_size"], help="Model size (default: large-v3)")
    parser.add_argument('--compute-type', default=DECODE_CONFIG["compute_type"], help="Compute type (default: int8)")
    args = parser.parse_args()

    # Find tag directory
    try:
        tag_dir = find_tag_dir(args.tag)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    print(f"{'='*60}")
    print(f"📝 DRAFT TRANSCRIPTION: {args.tag}")
    print(f"   Model: {args.model} ({args.compute_type}) on CPU")
    print(f"   Language: {DECODE_CONFIG['language']} (pinned)")
    print(f"   Target scenarios: {', '.join(SPONT_SCENARIOS)}")
    print(f"{'='*60}")

    # Load model
    print(f"\n🔄 Loading model {args.model} ({args.compute_type})...")
    start_load = time.time()
    model = WhisperModel(
        args.model,
        device=DECODE_CONFIG["device"],
        compute_type=args.compute_type,
        cpu_threads=2,  # Limit to 2 threads
        num_workers=1
    )
    print(f"✅ Model loaded in {time.time() - start_load:.1f}s")

    # Process each SPONT scenario
    for scenario_id in SPONT_SCENARIOS:
        wav_path = tag_dir / f"{scenario_id}.wav"
        draft_path = tag_dir / f"{scenario_id}.draft.json"

        if not wav_path.exists():
            print(f"\n⏭️  {scenario_id}: No 16k WAV found at {wav_path}, skipping")
            continue

        if draft_path.exists() and not args.force:
            print(f"\n⏭️  {scenario_id}: Draft already exists, skipping (use --force to re-transcribe)")
            continue

        print(f"\n📄 Transcribing {scenario_id}...")
        print(f"   Input: {wav_path.name}")

        # Load audio
        audio = load_audio_16k(wav_path)
        duration = len(audio) / 16000
        print(f"   Duration: {duration:.1f}s")

        # Transcribe with progress
        start_transcribe = time.time()
        segments = transcribe_audio(model, audio)
        transcribe_time = time.time() - start_transcribe
        rtf = transcribe_time / duration if duration > 0 else 0

        # Save draft
        draft_data = {
            "scenario_id": scenario_id,
            "tag": args.tag,
            "model": args.model,
            "compute_type": args.compute_type,
            "decode_config": DECODE_CONFIG,
            "audio_duration": duration,
            "transcribe_time": transcribe_time,
            "real_time_factor": rtf,
            "language": DECODE_CONFIG["language"],
            "segments": segments,
            "created_at": datetime.now().isoformat()
        }

        with open(draft_path, 'w', encoding='utf-8') as f:
            json.dump(draft_data, f, ensure_ascii=False, indent=2)

        print(f"   ✅ Done in {transcribe_time:.1f}s (RTF: {rtf:.2f}x)")
        print(f"   📊 {len(segments)} segments")
        print(f"   💾 Saved: {draft_path.name}")

        # Show first few segments
        for i, seg in enumerate(segments[:3]):
            print(f"     [{seg['start']:.1f}-{seg['end']:.1f}] (logprob={seg['avg_logprob']:.2f}) {seg['text'][:80]}")
        if len(segments) > 3:
            print(f"     ... and {len(segments) - 3} more segments")

    print(f"\n{'='*60}")
    print("✅ Draft transcription complete")
    print(f"\nNext step:")
    print(f"  python eval/correct_ui.py --tag {args.tag}")
    print(f"  (Then open http://<your-ip>:5001 to correct transcripts)")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())