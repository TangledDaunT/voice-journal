#!/usr/bin/env python3
"""
eval/score.py

Evaluate ASR systems against gold test set.
- Reads eval/systems.yaml for system definitions
- Runs each system on each scenario's 16k WAV
- Computes WER, CER, insertions/deletions/substitutions
- Real-time factor (processing time / audio duration)
- Repetition-loop detection (n-gram >30% or compression ratio >2.4)
- SILENCE scenario: hallucinated word count
- Outputs CSV + markdown summary table
- Highlights best system per scenario
"""

import argparse
import sys
import json
import time
import csv
import subprocess
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field

# Limit threads for CPU-only i3
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import numpy as np
import yaml
from jiwer import wer, cer, process_words, process_characters
from tqdm import tqdm

# Add parent for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from eval.normalize import Normalizer


# ============================
# Data Structures
# ============================
@dataclass
class SystemConfig:
    name: str
    audio_variant: str  # "raw16k" or ffmpeg filter chain
    model: str          # model path/name
    compute_type: str = "int8"
    device: str = "cpu"
    language: str = "hi"
    beam_size: int = 5
    temperature: List[float] = field(default_factory=lambda: [0.0, 0.2, 0.4])
    compression_ratio_threshold: float = 2.4
    log_prob_threshold: float = -1.0
    no_speech_threshold: float = 0.6
    vad_filter: bool = True
    condition_on_previous_text: bool = False
    word_timestamps: bool = True
    initial_prompt: str = ""
    # Derived
    ffmpeg_filter: Optional[str] = None

    @classmethod
    def from_dict(cls, name: str, data: Dict) -> 'SystemConfig':
        config = cls(
            name=name,
            audio_variant=data.get('audio_variant', 'raw16k'),
            model=data.get('model', 'large-v3'),
            compute_type=data.get('compute_type', 'int8'),
            device=data.get('device', 'cpu'),
            language=data.get('language', 'hi'),
            beam_size=data.get('beam_size', 5),
            temperature=data.get('temperature', [0.0, 0.2, 0.4]),
            compression_ratio_threshold=data.get('compression_ratio_threshold', 2.4),
            log_prob_threshold=data.get('log_prob_threshold', -1.0),
            no_speech_threshold=data.get('no_speech_threshold', 0.6),
            vad_filter=data.get('vad_filter', True),
            condition_on_previous_text=data.get('condition_on_previous_text', False),
            word_timestamps=data.get('word_timestamps', True),
            initial_prompt=data.get('initial_prompt', ''),
        )
        # Parse audio_variant for ffmpeg filter
        if config.audio_variant != 'raw16k':
            config.ffmpeg_filter = config.audio_variant
        return config


@dataclass
class ScenarioResult:
    scenario_id: str
    system_name: str
    wer: float
    cer: float
    insertions: int
    deletions: int
    substitutions: int
    ref_words: int
    hyp_words: int
    rtf: float
    processing_time: float
    audio_duration: float
    repetition_segments: int
    hallucinated_words: int  # For SILENCE scenario
    num_segments: int


# ============================
# Default Systems Configuration
# ============================
DEFAULT_SYSTEMS = {
    "baseline_current": {
        "audio_variant": "raw16k",
        "model": "small",  # From config: model_size: "small"
        "compute_type": "int8",
        "device": "cpu",
        "language": None,  # Auto-detect (from production config)
        "beam_size": 5,
        "temperature": [0.0],
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.5,
        "vad_filter": True,
        "condition_on_previous_text": False,
        "word_timestamps": True,
        "initial_prompt": "Shreyansh, Shivangi. Use only Hindi and English; do not output any other language.",
    },
    "large-v3_tuned": {
        "audio_variant": "raw16k",
        "model": "large-v3",
        "compute_type": "int8",
        "device": "cpu",
        "language": "hi",
        "beam_size": 5,
        "temperature": [0.0, 0.2, 0.4],
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.6,
        "vad_filter": True,
        "condition_on_previous_text": False,
        "word_timestamps": True,
        "initial_prompt": "Shreyansh, Shivangi. Use only Hindi and English; do not output any other language.",
    },
    "large-v2_tuned": {
        "audio_variant": "raw16k",
        "model": "large-v2",
        "compute_type": "int8",
        "device": "cpu",
        "language": "hi",
        "beam_size": 5,
        "temperature": [0.0, 0.2, 0.4],
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.6,
        "vad_filter": True,
        "condition_on_previous_text": False,
        "word_timestamps": True,
        "initial_prompt": "Shreyansh, Shivangi. Use only Hindi and English; do not output any other language.",
    },
}


# ============================
# Audio Processing
# ============================
def apply_audio_variant(input_wav: Path, output_wav: Path, variant: str) -> bool:
    """Apply audio variant (ffmpeg filter) to create processed audio."""
    if variant == 'raw16k':
        # Just copy
        import shutil
        shutil.copy2(input_wav, output_wav)
        return True

    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(input_wav),
            "-af", variant,
            "-ar", "16000", "-ac", "1",
            "-c:a", "pcm_s16le",
            str(output_wav)
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  ⚠️ ffmpeg failed for variant '{variant}': {e}")
        return False


def load_audio_16k(wav_path: Path) -> np.ndarray:
    """Load 16kHz WAV as float32 mono."""
    import soundfile as sf
    audio, sr = sf.read(wav_path, dtype='float32')
    if sr != 16000:
        from scipy.signal import resample_poly
        audio = resample_poly(audio, 16000, sr)
    if audio.ndim == 2:
        audio = audio[:, 0]
    return audio


# ============================
# Transcription
# ============================
def transcribe_with_model(model, audio: np.ndarray, config: SystemConfig) -> Tuple[List[Dict], float]:
    """Transcribe audio with given model and config. Returns (segments, processing_time)."""
    start = time.time()
    segments_gen, info = model.transcribe(
        audio,
        language=config.language,
        beam_size=config.beam_size,
        temperature=config.temperature,
        compression_ratio_threshold=config.compression_ratio_threshold,
        log_prob_threshold=config.log_prob_threshold,
        no_speech_threshold=config.no_speech_threshold,
        vad_filter=config.vad_filter,
        condition_on_previous_text=config.condition_on_previous_text,
        word_timestamps=config.word_timestamps,
        initial_prompt=config.initial_prompt,
    )
    processing_time = time.time() - start

    segments = []
    for seg in segments_gen:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
            "avg_logprob": seg.avg_logprob,
            "no_speech_prob": seg.no_speech_prob,
            "compression_ratio": seg.compression_ratio,
        })
    return segments, processing_time


def combine_segments_text(segments: List[Dict]) -> str:
    """Combine segment texts into single transcript."""
    return " ".join(seg['text'] for seg in segments if seg['text'].strip())


def detect_repetition_loops(segments: List[Dict], threshold: float = 0.3) -> int:
    """Count segments with repetition loops (n-gram >30% or compression_ratio >2.4)."""
    count = 0
    for seg in segments:
        text = seg['text'].strip()
        if not text:
            continue
        # Check compression ratio
        if seg.get('compression_ratio', 0) > 2.4:
            count += 1
            continue
        # Check n-gram repetition
        compact = "".join(text.split())
        if len(compact) < 12:
            continue
        for ngram_size in range(1, 5):
            counts = {}
            for i in range(len(compact) - ngram_size + 1):
                ngram = compact[i:i+ngram_size]
                counts[ngram] = counts.get(ngram, 0) + 1
            if counts:
                max_count = max(counts.values())
                covered = max_count * ngram_size / len(compact)
                min_repeats = 8 if ngram_size == 1 else 5
                if max_count >= min_repeats and covered > threshold:
                    count += 1
                    break
    return count


def count_hallucinated_words(segments: List[Dict]) -> int:
    """Count words in SILENCE scenario (should be zero)."""
    total = 0
    for seg in segments:
        text = seg['text'].strip()
        if text:
            total += len(text.split())
    return total


# ============================
# Evaluation
# ============================
def evaluate_scenario(
    system: SystemConfig,
    tag_dir: Path,
    scenario_id: str,
    normalizer: Normalizer,
    ref_text: str
) -> ScenarioResult:
    """Evaluate one system on one scenario."""

    # Load reference (already normalized)
    ref_normalized = normalizer.normalize(ref_text)

    # Prepare audio
    input_wav = tag_dir / f"{scenario_id}.wav"
    if not input_wav.exists():
        raise FileNotFoundError(f"Audio not found: {input_wav}")

    # Apply audio variant if needed
    if system.ffmpeg_filter:
        work_wav = tag_dir / f".tmp_{system.name}_{scenario_id}.wav"
        if not apply_audio_variant(input_wav, work_wav, system.ffmpeg_filter):
            raise RuntimeError(f"Failed to apply audio variant: {system.ffmpeg_filter}")
    else:
        work_wav = input_wav

    # Load audio
    audio = load_audio_16k(work_wav)
    audio_duration = len(audio) / 16000

    # Load model (cached per system)
    from faster_whisper import WhisperModel
    model = WhisperModel(
        system.model,
        device=system.device,
        compute_type=system.compute_type,
        cpu_threads=2,
        num_workers=1
    )

    # Transcribe
    segments, processing_time = transcribe_with_model(model, audio, system)

    # Combine hypothesis
    hyp_text = combine_segments_text(segments)
    hyp_normalized = normalizer.normalize(hyp_text)

    # Compute metrics
    if ref_normalized and hyp_normalized:
        word_measures = process_words(ref_normalized, hyp_normalized)
        char_measures = process_characters(ref_normalized, hyp_normalized)
        wer_score = word_measures.wer
        cer_score = char_measures.cer
        insertions = word_measures.insertions
        deletions = word_measures.deletions
        substitutions = word_measures.substitutions
        ref_words = word_measures.hits + word_measures.deletions + word_measures.substitutions
        hyp_words = word_measures.hits + word_measures.insertions + word_measures.substitutions
    else:
        wer_score = 1.0 if (ref_normalized or hyp_normalized) else 0.0
        cer_score = 1.0 if (ref_normalized or hyp_normalized) else 0.0
        insertions = len(hyp_normalized.split()) if hyp_normalized else 0
        deletions = len(ref_normalized.split()) if ref_normalized else 0
        substitutions = 0
        ref_words = len(ref_normalized.split()) if ref_normalized else 0
        hyp_words = len(hyp_normalized.split()) if hyp_normalized else 0

    rtf = processing_time / audio_duration if audio_duration > 0 else 0

    # Repetition detection
    repetition_segments = detect_repetition_loops(segments)

    # Hallucination detection (for SILENCE)
    hallucinated_words = count_hallucinated_words(segments) if scenario_id == "SILENCE" else 0

    # Cleanup temp file
    if system.ffmpeg_filter and work_wav.exists():
        work_wav.unlink()

    return ScenarioResult(
        scenario_id=scenario_id,
        system_name=system.name,
        wer=wer_score,
        cer=cer_score,
        insertions=insertions,
        deletions=deletions,
        substitutions=substitutions,
        ref_words=ref_words,
        hyp_words=hyp_words,
        rtf=rtf,
        processing_time=processing_time,
        audio_duration=audio_duration,
        repetition_segments=repetition_segments,
        hallucinated_words=hallucinated_words,
        num_segments=len(segments)
    )


def load_reference(tag_dir: Path, scenario_id: str) -> Optional[str]:
    """Load reference text for a scenario."""
    # For scripted scenarios, load from scripts.yaml
    if scenario_id in ["SCRIPTED_HI", "SCRIPTED_EN", "SCRIPTED_HINGLISH"]:
        scripts_path = Path(__file__).parent / "scripts.yaml"
        with open(scripts_path, 'r', encoding='utf-8') as f:
            scripts = yaml.safe_load(f)
        key = scenario_id.replace("SCRIPTED_", "scripted_").lower()
        if key in scripts:
            return "\n".join(scripts[key])
        return ""

    # For SPONT_* scenarios, load from .ref.txt
    ref_path = tag_dir / f"{scenario_id}.ref.txt"
    if not ref_path.exists():
        return None
    with open(ref_path, 'r', encoding='utf-8') as f:
        lines = f.read().strip().split('\n')
    # Filter out unintelligible markers
    texts = [line for line in lines if line != "[[UNINTELLIGIBLE]]"]
    return " ".join(texts)


def load_systems_yaml(systems_path: Path) -> Dict[str, SystemConfig]:
    """Load systems from YAML, creating defaults if not exists."""
    systems_path = Path(systems_path)
    if systems_path.exists():
        with open(systems_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if data and 'systems' in data:
            systems = {}
            for name, config in data['systems'].items():
                systems[name] = SystemConfig.from_dict(name, config)
            return systems

    # Create default systems.yaml
    systems = {name: SystemConfig.from_dict(name, config) for name, config in DEFAULT_SYSTEMS.items()}
    data = {'systems': {name: vars(config) for name, config in systems.items()}}
    with open(systems_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return systems


# ============================
# Main
# ============================
def main():
    parser = argparse.ArgumentParser(
        description="Evaluate ASR systems against gold test set",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval/score.py --tag desk
  python eval/score.py --tag lav --systems eval/systems.yaml --output eval/results/
        """
    )
    parser.add_argument('--tag', required=True, help="Tag for the recording session")
    parser.add_argument('--systems', default='eval/systems.yaml', help="Systems YAML config")
    parser.add_argument('--output', default='eval/results', help="Output directory for results")
    parser.add_argument('--only-systems', nargs='+', help="Only evaluate specific systems")
    parser.add_argument('--only-scenarios', nargs='+', help="Only evaluate specific scenarios")
    parser.add_argument('--variants', default='eval/variants.yaml', help="Variants YAML for normalization")
    args = parser.parse_args()

    tag_dir = Path(__file__).parent / args.tag
    if not tag_dir.exists():
        print(f"❌ Tag directory not found: {tag_dir}")
        return 1

    systems_path = Path(args.systems)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load systems
    systems = load_systems_yaml(systems_path)
    if args.only_systems:
        systems = {k: v for k, v in systems.items() if k in args.only_systems}

    # Load normalizer
    normalizer = Normalizer(Path(args.variants))

    # Scenarios to evaluate
    all_scenarios = [
        "SCRIPTED_HI", "SCRIPTED_EN", "SCRIPTED_HINGLISH",
        "SPONT_SOLO", "SPONT_CONVO", "SPONT_QUIET_FAR", "SPONT_NOISY", "SILENCE"
    ]
    if args.only_scenarios:
        scenarios = [s for s in all_scenarios if s in args.only_scenarios]
    else:
        scenarios = all_scenarios

    print(f"{'='*60}")
    print(f"📊 EVALUATION: {args.tag}")
    print(f"   Systems: {', '.join(systems.keys())}")
    print(f"   Scenarios: {', '.join(scenarios)}")
    print(f"{'='*60}")

    # Load references
    references = {}
    for scenario_id in scenarios:
        ref = load_reference(tag_dir, scenario_id)
        if ref is None:
            print(f"  ⚠️  No reference for {scenario_id}, skipping")
            continue
        references[scenario_id] = ref
        print(f"  ✅ {scenario_id}: {len(ref.split())} words (ref)")

    if not references:
        print("❌ No valid references found")
        return 1

    # Evaluate each system on each scenario
    all_results = []
    for system_name, system in systems.items():
        print(f"\n🔄 Evaluating system: {system_name}")
        print(f"   Model: {system.model} ({system.compute_type})")
        print(f"   Audio variant: {system.audio_variant}")

        for scenario_id in tqdm(scenarios, desc=f"  {system_name}", leave=False):
            if scenario_id not in references:
                continue
            try:
                result = evaluate_scenario(system, tag_dir, scenario_id, normalizer, references[scenario_id])
                all_results.append(result)
            except Exception as e:
                print(f"  ❌ {scenario_id}: {e}")
                all_results.append(ScenarioResult(
                    scenario_id=scenario_id,
                    system_name=system_name,
                    wer=1.0, cer=1.0, insertions=0, deletions=0, substitutions=0,
                    ref_words=0, hyp_words=0, rtf=0, processing_time=0, audio_duration=0,
                    repetition_segments=0, hallucinated_words=0, num_segments=0
                ))

    # Write CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"{args.tag}_{timestamp}.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'scenario', 'system', 'wer', 'cer', 'insertions', 'deletions', 'substitutions',
            'ref_words', 'hyp_words', 'rtf', 'processing_time', 'audio_duration',
            'repetition_segments', 'hallucinated_words', 'num_segments'
        ])
        for r in all_results:
            writer.writerow([
                r.scenario_id, r.system_name, f"{r.wer:.4f}", f"{r.cer:.4f}",
                r.insertions, r.deletions, r.substitutions,
                r.ref_words, r.hyp_words, f"{r.rtf:.3f}", f"{r.processing_time:.2f}",
                f"{r.audio_duration:.2f}", r.repetition_segments,
                r.hallucinated_words, r.num_segments
            ])
    print(f"\n💾 CSV saved: {csv_path}")

    # Generate markdown summary
    md_path = output_dir / f"{args.tag}_{timestamp}.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f"# Evaluation Results: {args.tag}\n\n")
        f.write(f"**Date:** {datetime.now().isoformat()}\n")
        f.write(f"**Systems:** {', '.join(systems.keys())}\n\n")

        # Per-scenario tables
        for scenario_id in scenarios:
            if scenario_id not in references:
                continue
            f.write(f"## {scenario_id}\n\n")
            f.write("| System | WER | CER | Ins | Del | Sub | RTF | Repetitions | Hallucinations |\n")
            f.write("|--------|-----|-----|-----|-----|-----|-----|-------------|----------------|\n")

            scenario_results = [r for r in all_results if r.scenario_id == scenario_id]
            # Sort by WER (best first)
            scenario_results.sort(key=lambda x: x.wer)

            for i, r in enumerate(scenario_results):
                best_marker = " 🏆" if i == 0 else ""
                f.write(f"| {r.system_name} | {r.wer:.2%} | {r.cer:.2%} | {r.insertions} | {r.deletions} | {r.substitutions} | {r.rtf:.2f}x | {r.repetition_segments} | {r.hallucinated_words} |\n")
            f.write("\n")

        # Overall summary
        f.write("## Overall Ranking (Average WER across scenarios)\n\n")
        f.write("| System | Avg WER | Avg CER | Avg RTF | Scenarios Evaluated |\n")
        f.write("|--------|---------|---------|---------|---------------------|\n")

        system_stats = {}
        for r in all_results:
            if r.system_name not in system_stats:
                system_stats[r.system_name] = {'wers': [], 'cers': [], 'rtfs': [], 'count': 0}
            system_stats[r.system_name]['wers'].append(r.wer)
            system_stats[r.system_name]['cers'].append(r.cer)
            system_stats[r.system_name]['rtfs'].append(r.rtf)
            system_stats[r.system_name]['count'] += 1

        ranked = sorted(system_stats.items(), key=lambda x: np.mean(x[1]['wers']))
        for i, (name, stats) in enumerate(ranked):
            best = " 🏆" if i == 0 else ""
            f.write(f"| {name} | {np.mean(stats['wers']):.2%} | {np.mean(stats['cers']):.2%} | {np.mean(stats['rtfs']):.2f}x | {stats['count']} |\n")

    print(f"📄 Markdown saved: {md_path}")

    # Print summary table to terminal
    print(f"\n{'='*80}")
    print("📊 SUMMARY TABLE")
    print(f"{'='*80}")

    for scenario_id in scenarios:
        if scenario_id not in references:
            continue
        scenario_results = [r for r in all_results if r.scenario_id == scenario_id]
        scenario_results.sort(key=lambda x: x.wer)

        print(f"\n{scenario_id}:")
        print(f"  {'System':<20} {'WER':>8} {'CER':>8} {'RTF':>6} {'Rep':>4} {'Hall':>4}")
        print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*6} {'-'*4} {'-'*4}")
        for i, r in enumerate(scenario_results):
            marker = " 🏆" if i == 0 else ""
            print(f"  {r.system_name:<20} {r.wer:>7.2%} {r.cer:>7.2%} {r.rtf:>5.2f}x {r.repetition_segments:>4} {r.hallucinated_words:>4}{marker}")

    print(f"\n{'='*80}")
    print(f"Best overall (avg WER): {ranked[0][0]} 🏆")
    print(f"Results saved to: {output_dir}")
    print(f"{'='*80}")

    return 0


if __name__ == "__main__":
    sys.exit(main())