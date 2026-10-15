#!/usr/bin/env python3
"""
eval/record_gold.py

Guided gold-set recording for voice journal evaluation.
Records at 48 kHz mono 16-bit FLAC (lossless) + 16 kHz WAV derived copy.
Live level meter, clipping warning, SNR estimation.
Saves under eval/<tag>/ with per-scenario FLAC/WAV files.
"""

import argparse
import sys
import os
import time
import signal
import wave
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
import yaml
import numpy as np
import sounddevice as sd
import soundfile as sf

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================
# Audio Configuration
# ============================
RECORD_SR = 48000          # Recording sample rate (Hz)
RECORD_CHANNELS = 1        # Mono
RECORD_DTYPE = 'int16'     # 16-bit
TARGET_SR = 16000          # Derived copy sample rate
FRAME_MS = 50              # Frame size for level meter (ms)
CLIP_THRESHOLD_DBFS = -0.5 # Clipping warning threshold (dBFS)
SNR_FRAME_MS = 50          # Frame size for SNR estimation (ms)
SNR_NOISE_PERCENTILE = 10  # Noise floor = 10th percentile of frame RMS

# Derived
FRAME_SAMPLES = int(RECORD_SR * FRAME_MS / 1000)
SNR_FRAME_SAMPLES = int(RECORD_SR * SNR_FRAME_MS / 1000)


# ============================
# Utilities
# ============================
def db20(x: float) -> float:
    """Convert linear amplitude to dBFS (20*log10)."""
    if x <= 0:
        return -120.0
    return 20.0 * np.log10(x)


def rms_db(audio: np.ndarray) -> float:
    """RMS in dBFS."""
    return db20(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))


def print_level_meter(level_db: float, clipped: bool, width: int = 40):
    """Print a horizontal level meter in the terminal."""
    # Map -60..0 dBFS to 0..width
    normalized = max(0.0, min(1.0, (level_db + 60.0) / 60.0))
    filled = int(normalized * width)
    bar = "█" * filled + "░" * (width - filled)
    clip_marker = " ⚠️ CLIP" if clipped else ""
    sys.stdout.write(f"\r[{bar}] {level_db:6.1f} dBFS{clip_marker}")
    sys.stdout.flush()


def estimate_snr(audio: np.ndarray, sr: int) -> Tuple[float, float, float]:
    """
    Estimate SNR using frame-based method.
    Noise floor = 10th percentile of frame RMS.
    Signal = median of top 30% frames.
    Returns (snr_db, signal_db, noise_db).
    """
    frame_len = SNR_FRAME_SAMPLES
    hop_len = frame_len // 2
    n_frames = (len(audio) - frame_len) // hop_len + 1

    if n_frames < 10:
        return 0.0, rms_db(audio), -120.0

    frame_rms = []
    for i in range(n_frames):
        start = i * hop_len
        end = start + frame_len
        frame = audio[start:end]
        frame_rms.append(rms_db(frame))

    frame_rms = np.array(frame_rms)
    noise_db = np.percentile(frame_rms, SNR_NOISE_PERCENTILE)
    # Signal = median of top 30% frames
    threshold = np.percentile(frame_rms, 70)
    signal_frames = frame_rms[frame_rms >= threshold]
    signal_db = np.median(signal_frames) if len(signal_frames) > 0 else np.max(frame_rms)

    snr_db = signal_db - noise_db
    return max(0.0, snr_db), signal_db, noise_db


def resample_to_16k(input_path: Path, output_path: Path) -> bool:
    """Resample FLAC to 16 kHz mono WAV using ffmpeg (fast, high quality)."""
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(input_path),
            "-ar", str(TARGET_SR), "-ac", "1",
            "-c:a", "pcm_s16le",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"\n  ⚠️ ffmpeg failed ({e}), falling back to soundfile...")
        try:
            data, sr = sf.read(input_path)
            if sr != TARGET_SR:
                # Simple linear resample via scipy if available
                try:
                    from scipy.signal import resample_poly
                    data = resample_poly(data, TARGET_SR, sr)
                except ImportError:
                    # Naive decimation (not ideal but works for 48k->16k = 3:1)
                    data = data[::3]
            sf.write(output_path, data, TARGET_SR, subtype='PCM_16')
            return True
        except Exception as e2:
            print(f"  ❌ Resample failed: {e2}")
            return False


def countdown(seconds: int, message: str = "Starting in"):
    """Print a countdown."""
    for i in range(seconds, 0, -1):
        sys.stdout.write(f"\r{message} {i}... ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()


def record_audio(
    duration: Optional[float] = None,
    stop_on_silence: bool = False,
    silence_threshold_db: float = -50.0,
    min_silence_duration: float = 2.0
) -> Tuple[np.ndarray, float]:
    """
    Record audio with live level meter.
    Returns (audio_data, actual_duration).
    If duration is None, records until Enter pressed (or silence if stop_on_silence).
    """
    audio_chunks = []
    clipped = False
    silence_frames = 0
    silence_frame_limit = int(min_silence_duration * 1000 / FRAME_MS)

    def callback(indata, frames, time_info, status):
        nonlocal clipped, silence_frames
        if status:
            pass  # Ignore overflow/underflow for now
        chunk = indata[:, 0].copy()  # Mono
        audio_chunks.append(chunk)

        # Level meter
        level = rms_db(chunk)
        if level > CLIP_THRESHOLD_DBFS:
            clipped = True
        print_level_meter(level, clipped)

        # Silence detection
        if stop_on_silence and level < silence_threshold_db:
            silence_frames += 1
        else:
            silence_frames = 0

    print("\n🎙️  Recording... (Press Enter to stop)")
    if duration:
        print(f"   Target duration: {duration:.0f}s")
    sys.stdout.flush()

    stream = sd.InputStream(
        samplerate=RECORD_SR,
        channels=RECORD_CHANNELS,
        dtype=RECORD_DTYPE,
        blocksize=FRAME_SAMPLES,
        callback=callback
    )

    start_time = time.time()
    stream.start()

    try:
        if duration:
            # Timed recording with early stop on Enter
            import threading
            stop_event = threading.Event()

            def wait_for_enter():
                input()
                stop_event.set()

            t = threading.Thread(target=wait_for_enter, daemon=True)
            t.start()

            while not stop_event.is_set() and (time.time() - start_time) < duration:
                if stop_on_silence and silence_frames >= silence_frame_limit:
                    print(f"\n  Silence detected for {min_silence_duration}s, stopping...")
                    break
                time.sleep(0.1)
        else:
            # Manual stop
            input()
    except KeyboardInterrupt:
        print("\n  Interrupted")
    finally:
        stream.stop()
        stream.close()

    actual_duration = time.time() - start_time
    print()  # Newline after level meter

    if not audio_chunks:
        return np.array([], dtype=np.int16), 0.0

    audio = np.concatenate(audio_chunks)
    return audio, actual_duration


def save_flac(audio: np.ndarray, sr: int, path: Path):
    """Save audio as FLAC (lossless)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, sr, format='FLAC', subtype='PCM_16')


def load_scripts_yaml() -> dict:
    """Load scripts.yaml from eval directory."""
    scripts_path = Path(__file__).parent / "scripts.yaml"
    with open(scripts_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def record_scenario(
    tag_dir: Path,
    scenario: dict,
    script_text: Optional[str] = None,
    force: bool = False
) -> Optional[Path]:
    """Record a single scenario. Returns path to FLAC file or None if skipped."""
    scenario_id = scenario['id']
    flac_path = tag_dir / f"{scenario_id}.flac"
    wav_path = tag_dir / f"{scenario_id}.wav"

    # Check if already exists
    if flac_path.exists() and not force:
        print(f"  ⏭️  {scenario_id} already exists, skipping (use --force to re-record)")
        return flac_path

    print(f"\n{'='*60}")
    print(f"📋 Scenario: {scenario['name']} ({scenario_id})")
    print(f"   {scenario['description']}")
    print(f"   Duration hint: {scenario['duration_hint']}")

    if script_text:
        print(f"\n📖 Script to read:")
        print(f"   {script_text}")

    # Countdown
    countdown(3, "Get ready")

    # Determine recording mode
    if scenario_id == "SILENCE":
        duration = 60.0
        stop_on_silence = False
    elif scenario_id in ["SPONT_SOLO", "SPONT_CONVO"]:
        duration = 180.0  # 3 min
        stop_on_silence = False
    elif scenario_id in ["SPONT_QUIET_FAR", "SPONT_NOISY"]:
        duration = 120.0  # 2 min
        stop_on_silence = False
    else:
        # Scripted - no fixed duration, stop on Enter
        duration = None
        stop_on_silence = False

    # Record
    audio, actual_duration = record_audio(
        duration=duration,
        stop_on_silence=stop_on_silence
    )

    if len(audio) == 0:
        print("  ❌ No audio recorded")
        return None

    print(f"  ✅ Recorded {actual_duration:.1f}s ({len(audio)/RECORD_SR:.1f}s at {RECORD_SR}Hz)")

    # Save FLAC
    save_flac(audio, RECORD_SR, flac_path)
    print(f"  💾 Saved FLAC: {flac_path.name}")

    # Resample to 16k WAV
    print(f"  🔄 Resampling to {TARGET_SR}Hz WAV...")
    if resample_to_16k(flac_path, wav_path):
        print(f"  💾 Saved WAV: {wav_path.name}")
    else:
        print(f"  ❌ Failed to create 16k WAV")

    # Analyze
    snr_db, signal_db, noise_db = estimate_snr(audio, RECORD_SR)
    peak_db = rms_db(audio)
    max_amplitude = np.max(np.abs(audio.astype(np.float32))) / 32768.0
    clipped = max_amplitude >= 0.99

    print(f"  📊 Peak: {peak_db:.1f} dBFS, Signal: {signal_db:.1f} dBFS, Noise floor: {noise_db:.1f} dBFS, SNR: {snr_db:.1f} dB")
    if clipped:
        print(f"  ⚠️  WARNING: Clipping detected!")

    return flac_path


def main():
    parser = argparse.ArgumentParser(
        description="Record gold test set for voice journal evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval/record_gold.py --tag desk
  python eval/record_gold.py --tag lav --force
  python eval/record_gold.py --tag desk --only SCRIPTED_HI SPONT_SOLO
        """
    )
    parser.add_argument('--tag', help="Tag for this recording session (e.g., desk, lav)")
    parser.add_argument('--force', action='store_true', help="Re-record even if files exist")
    parser.add_argument('--only', nargs='+', help="Only record specific scenario IDs")
    parser.add_argument('--skip', nargs='+', help="Skip specific scenario IDs")
    parser.add_argument('--list', action='store_true', help="List scenarios and exit")
    args = parser.parse_args()

    # Load scripts
    scripts = load_scripts_yaml()
    scenarios = scripts['scenarios']
    scripted_hi = scripts['scripted_hi']
    scripted_en = scripts['scripted_en']
    scripted_hinglish = scripts['scripted_hinglish']

    if args.list:
        print("Available scenarios:")
        for s in scenarios:
            print(f"  {s['id']}: {s['name']} - {s['description']}")
        return 0

    # Validate tag
    if not args.tag:
        print("❌ --tag is required (except with --list)")
        return 1
    tag = args.tag.strip().replace('/', '_').replace('\\', '_')

    tag_dir = Path(__file__).parent / tag
    tag_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"🎙️  GOLD SET RECORDING: {tag}")
    print(f"   Output directory: {tag_dir}")
    print(f"   Sample rate: {RECORD_SR}Hz mono 16-bit FLAC + {TARGET_SR}Hz WAV")
    print(f"{'='*60}")

    # Check audio devices
    print("\n🔍 Available input devices:")
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            marker = " ← DEFAULT" if i == sd.default.device[0] else ""
            print(f"  [{i}] {dev['name']}{marker} ({dev['max_input_channels']} ch)")

    # Confirm device
    try:
        sd.check_input_settings(samplerate=RECORD_SR, channels=RECORD_CHANNELS, dtype=RECORD_DTYPE)
        print(f"\n✅ Default device supports {RECORD_SR}Hz mono int16")
    except Exception as e:
        print(f"\n❌ Default device check failed: {e}")
        return 1

    # Filter scenarios
    selected = scenarios
    if args.only:
        only_set = set(args.only)
        selected = [s for s in scenarios if s['id'] in only_set]
        if not selected:
            print(f"❌ No matching scenarios for --only {args.only}")
            return 1
    if args.skip:
        skip_set = set(args.skip)
        selected = [s for s in selected if s['id'] not in skip_set]

    print(f"\n📝 Will record {len(selected)} scenario(s):")
    for s in selected:
        print(f"   - {s['id']}: {s['name']}")

    input("\nPress Enter to start recording...")

    # Record each scenario
    results = []
    for scenario in selected:
        scenario_id = scenario['id']

        # Get script text for scripted scenarios
        script_text = None
        if scenario_id == "SCRIPTED_HI":
            script_text = "\n   ".join(scripted_hi)
        elif scenario_id == "SCRIPTED_EN":
            script_text = "\n   ".join(scripted_en)
        elif scenario_id == "SCRIPTED_HINGLISH":
            script_text = "\n   ".join(scripted_hinglish)

        flac_path = record_scenario(tag_dir, scenario, script_text, args.force)
        results.append((scenario_id, flac_path is not None))

        # Allow re-take
        if flac_path and scenario.get('re_record_allowed', True):
            while True:
                choice = input("\n  Re-record? (y/n/q=quit): ").strip().lower()
                if choice in ('n', 'no', ''):
                    break
                elif choice in ('y', 'yes'):
                    flac_path = record_scenario(tag_dir, scenario, script_text, force=True)
                    results[-1] = (scenario_id, flac_path is not None)
                elif choice in ('q', 'quit'):
                    print("\n👋 Recording session ended by user")
                    return 0
                else:
                    print("  Please enter y, n, or q")

    # Summary
    print(f"\n{'='*60}")
    print("📋 RECORDING SUMMARY")
    print(f"{'='*60}")
    for scenario_id, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {scenario_id}")

    print(f"\n📁 Files saved to: {tag_dir}")
    print("\nNext steps:")
    print(f"  1. ./vj-control.sh start  (restart daemon if stopped)")
    print(f"  2. python eval/draft_transcribe.py --tag {tag}")
    print(f"  3. python eval/correct_ui.py --tag {tag}")
    print(f"  4. python eval/score.py --tag {tag}")

    return 0


if __name__ == "__main__":
    sys.exit(main())