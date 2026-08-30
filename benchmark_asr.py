#!/usr/bin/env python3
"""
Fix 0: Benchmark script for faster-whisper large-v3 on target hardware.

Measures actual RTF (Real-Time Factor) for large-v3/int8 on sample audio clips.
This feeds into Fix 8's backlog thresholds.

Usage:
    python benchmark_asr.py [audio_files...] [--output benchmark_results.json]

If no audio files provided, generates synthetic test clips of varying lengths.
"""

import argparse
import json
import time
import tempfile
import numpy as np
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional
import subprocess
import sys

# Try imports early to give clear errors
try:
    from faster_whisper import WhisperModel
except ImportError:
    print("ERROR: faster-whisper not installed. Run: pip install faster-whisper")
    sys.exit(1)

try:
    import librosa
except ImportError:
    print("ERROR: librosa not installed. Run: pip install librosa")
    sys.exit(1)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    model_size: str
    compute_type: str
    audio_file: str
    audio_duration_seconds: float
    processing_time_seconds: float
    real_time_factor: float
    device: str

    # Transcript metadata
    transcript_length: int
    language_detected: str
    language_probability: float

    # System info
    cpu_info: str
    memory_gb: float


def get_system_info() -> dict:
    """Get system information for benchmark context."""
    import platform
    import psutil

    # CPU info
    if platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
            # Get model name
            for line in cpuinfo.split("\n"):
                if "model name" in line.lower():
                    cpu_model = line.split(":")[1].strip()
                    break
            else:
                cpu_model = platform.processor() or "Unknown"
        except:
            cpu_model = platform.processor() or "Unknown"
    else:
        cpu_model = platform.processor() or "Unknown"

    return {
        "cpu_info": cpu_model,
        "memory_gb": psutil.virtual_memory().total / (1024**3),
        "platform": platform.system(),
        "python_version": platform.python_version()
    }


def generate_test_audio(duration_seconds: float, sample_rate: int = 16000) -> np.ndarray:
    """
    Generate synthetic audio for testing.
    This is just noise - for real benchmarks, use actual speech audio.
    """
    # Generate pink noise (more natural than white noise)
    samples = int(duration_seconds * sample_rate)

    # Pink noise generation using the Voss-McCartney algorithm
    pink_noise = np.zeros(samples)
    b = [0.0] * 7

    for i in range(samples):
        white = np.random.random() * 2 - 1
        b[0] = 0.99886 * b[0] + white * 0.0555179
        b[1] = 0.99332 * b[1] + white * 0.0750759
        b[2] = 0.96900 * b[2] + white * 0.1538520
        b[3] = 0.86650 * b[3] + white * 0.3104856
        b[4] = 0.55000 * b[4] + white * 0.5329522
        b[5] = -0.7616 * b[5] - white * 0.0168980
        pink_noise[i] = b[0] + b[1] + b[2] + b[3] + b[4] + b[5] + b[6] + white * 0.5362
        b[6] = white * 0.115926

    # Normalize to reasonable level
    pink_noise = pink_noise / (np.max(np.abs(pink_noise)) + 1e-8) * 0.3

    return pink_noise.astype(np.float32)


def benchmark_model(
    model_size: str,
    compute_type: str,
    audio: np.ndarray,
    audio_name: str,
    audio_duration: float,
    device: str = "cpu"
) -> BenchmarkResult:
    """
    Benchmark a model configuration on a single audio clip.
    """
    print(f"\n  Benchmarking {model_size}/{compute_type} on {audio_name}...")

    # Load model
    load_start = time.time()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    load_time = time.time() - load_start
    print(f"    Model load time: {load_time:.2f}s")

    # Transcribe
    transcribe_start = time.time()
    segments, info = model.transcribe(
        audio,
        language=None,  # Auto-detect
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
        temperature=0.0
    )

    # Consume generator
    segments_list = list(segments)
    transcribe_time = time.time() - transcribe_start

    # Calculate RTF
    rtf = transcribe_time / audio_duration if audio_duration > 0 else 0

    # Get transcript info
    transcript = " ".join(seg.text for seg in segments_list if seg)
    sys_info = get_system_info()

    result = BenchmarkResult(
        model_size=model_size,
        compute_type=compute_type,
        audio_file=audio_name,
        audio_duration_seconds=audio_duration,
        processing_time_seconds=transcribe_time,
        real_time_factor=rtf,
        device=device,
        transcript_length=len(transcript),
        language_detected=info.language,
        language_probability=info.language_probability,
        cpu_info=sys_info["cpu_info"],
        memory_gb=sys_info["memory_gb"]
    )

    print(f"    Processing time: {transcribe_time:.2f}s")
    print(f"    RTF: {rtf:.2f}x")
    print(f"    Language: {info.language} ({info.language_probability:.2f})")

    return result


def run_benchmarks(
    audio_files: List[str],
    models: List[str] = None,
    compute_types: List[str] = None,
    output_file: Optional[str] = None
) -> List[BenchmarkResult]:
    """
    Run benchmarks across multiple models and audio files.
    """
    if models is None:
        models = ["large-v3", "distil-large-v3"]

    if compute_types is None:
        compute_types = ["int8"]

    results = []
    system_info = get_system_info()

    print("="*60)
    print("ASR Benchmark Script")
    print("="*60)
    print(f"System: {system_info['cpu_info']}")
    print(f"Memory: {system_info['memory_gb']:.1f} GB")
    print(f"Platform: {system_info['platform']}")
    print("="*60)

    # Test clips dictionary: name -> (audio, duration)
    test_clips = {}

    if audio_files:
        # Use provided audio files
        for audio_path in audio_files:
            path = Path(audio_path)
            if not path.exists():
                print(f"WARNING: {audio_path} not found, skipping")
                continue

            print(f"\nLoading {path.name}...")
            audio, sr = librosa.load(str(path), sr=16000, mono=True)
            duration = len(audio) / sr
            test_clips[path.name] = (audio, duration)

    else:
        # Generate synthetic test clips of various lengths
        print("\nNo audio files provided. Generating synthetic test clips...")
        print("(For real benchmarks, provide actual speech audio files)")

        test_durations = [10, 30, 60, 120]  # 10s, 30s, 1min, 2min

        for duration in test_durations:
            print(f"  Generating {duration}s test clip...")
            audio = generate_test_audio(duration)
            test_clips[f"synthetic_{duration}s"] = (audio, float(duration))

    print(f"\nRunning benchmarks for {len(test_clips)} test clips...")
    print(f"Models: {models}")
    print(f"Compute types: {compute_types}")

    # Run benchmarks
    for model_size in models:
        for compute_type in compute_types:
            for clip_name, (audio, duration) in test_clips.items():
                try:
                    result = benchmark_model(
                        model_size=model_size,
                        compute_type=compute_type,
                        audio=audio,
                        audio_name=clip_name,
                        audio_duration=duration,
                        device="cpu"
                    )
                    results.append(result)

                except Exception as e:
                    print(f"  ERROR: {e}")
                    continue

    # Calculate summary statistics
    print("\n" + "="*60)
    print("BENCHMARK RESULTS SUMMARY")
    print("="*60)

    # Group by model
    from collections import defaultdict
    by_model = defaultdict(list)
    for r in results:
        by_model[r.model_size].append(r)

    for model, model_results in by_model.items():
        avg_rtf = np.mean([r.real_time_factor for r in model_results])
        print(f"\n{model}:")
        print(f"  Average RTF: {avg_rtf:.2f}x")
        print(f"  Results: {len(model_results)}")

        # Extrapolate for daily speech volume
        daily_speech_hours = 4.5  # Midpoint of 3-6 hours
        daily_processing_hours = avg_rtf * daily_speech_hours
        print(f"\n  With {daily_speech_hours}h daily speech volume:")
        print(f"    Expected processing time: {daily_processing_hours:.1f}h")
        print(f"    Can process overnight (8h window): {'YES' if daily_processing_hours <= 8 else 'NO - NEEDS FALLBACK'}")

    # Save results
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        results_dict = {
            "system_info": system_info,
            "results": [asdict(r) for r in results],
            "summary": {
                "models_tested": models,
                "compute_types_tested": compute_types,
                "total_benchmarks": len(results),
                "daily_speech_assumption_hours": 4.5,
            }
        }

        with open(output_path, "w") as f:
            json.dump(results_dict, f, indent=2)

        print(f"\nResults saved to: {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark faster-whisper models on target hardware"
    )
    parser.add_argument(
        "audio_files",
        nargs="*",
        help="Audio files to benchmark (optional, will generate synthetic if not provided)"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["large-v3", "distil-large-v3"],
        help="Models to benchmark (default: large-v3 distil-large-v3)"
    )
    parser.add_argument(
        "--compute-types",
        nargs="+",
        default=["int8"],
        help="Compute types to test (default: int8)"
    )
    parser.add_argument(
        "--output", "-o",
        default="benchmark_results.json",
        help="Output JSON file for results"
    )

    args = parser.parse_args()

    results = run_benchmarks(
        audio_files=args.audio_files,
        models=args.models,
        compute_types=args.compute_types,
        output_file=args.output
    )

    print("\nBenchmark complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
