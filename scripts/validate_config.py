"""Configuration validation script.

Checks that config is valid and all dependencies are installed.
"""

import sys
from pathlib import Path

from config.settings import Config


def check_dependencies():
    """Check that required dependencies are installed."""
    missing = []

    # Core dependencies
    try:
        import numpy
    except ImportError:
        missing.append("numpy")

    try:
        import sounddevice
    except ImportError:
        missing.append("sounddevice")

    try:
        import librosa
    except ImportError:
        missing.append("librosa")

    # VAD
    try:
        import torch
    except ImportError:
        missing.append("torch")

    # ASR
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        missing.append("faster-whisper")

    # LLM
    try:
        import requests
    except ImportError:
        missing.append("requests")

    # Audio preprocessing
    try:
        import noisereduce
    except ImportError:
        missing.append("noisereduce (optional, for denoising)")
        # Not critical

    # Speaker embeddings
    try:
        from resemblyzer import VoiceEncoder
    except ImportError:
        missing.append("resemblyzer (optional, for speaker ID)")

    # System monitoring
    try:
        import psutil
    except ImportError:
        missing.append("psutil (required for scheduler)")

    return missing


def check_config(config_path: str = None):
    """Validate configuration file."""
    issues = []

    try:
        if config_path:
            config = Config.from_yaml(config_path)
        else:
            config = Config()

        # Check model size
        valid_sizes = ["tiny", "base", "small", "medium", "large-v3", "large-v2", "distil-large-v3"]
        if config.asr.model_size not in valid_sizes:
            issues.append(f"Invalid ASR model_size: {config.asr.model_size}")

        # Check compute type
        valid_compute = ["int8", "int16", "float16", "float32"]
        if config.asr.compute_type not in valid_compute:
            issues.append(f"Invalid ASR compute_type: {config.asr.compute_type}")

        # Check directories exist or can be created
        paths_to_check = [
            config.audio.audio_storage_path,
            config.obsidian.vault_path,
            config.database.path
        ]

        for path_str in paths_to_check:
            path = Path(path_str)
            if not path.exists():
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    issues.append(f"Cannot create directory {path}: {e}")

        # Check scheduler config
        if config.scheduler.cpu_idle_threshold > 100 or config.scheduler.cpu_idle_threshold < 0:
            issues.append(f"Invalid cpu_idle_threshold: {config.scheduler.cpu_idle_threshold}")

        if config.scheduler.daytime_batch_hours <= 0:
            issues.append(f"Invalid daytime_batch_hours: {config.scheduler.daytime_batch_hours}")

        if config.scheduler.overnight_batch_hours <= 0:
            issues.append(f"Invalid overnight_batch_hours: {config.scheduler.overnight_batch_hours}")

        return config, issues

    except Exception as e:
        return None, [f"Failed to load config: {e}"]


def check_voice_profiles(config: Config):
    """Check that voice profiles exist."""
    issues = []

    from pathlib import Path
    profile_path = Path(config.speaker.calibration_file)

    if not profile_path.exists():
        issues.append(f"Voice profiles not found at {profile_path}")
        issues.append("  Run: python -m speaker_id.embedding_speaker_id --shreyansh <audio> --shivangi <audio>")
    else:
        try:
            import json
            with open(profile_path) as f:
                profiles = json.load(f)

            if "shreyansh" not in profiles:
                issues.append("Missing 'shreyansh' in voice profiles")

            if "shivangi" not in profiles:
                issues.append("Missing 'shivangi' in voice profiles")

        except Exception as e:
            issues.append(f"Failed to load voice profiles: {e}")

    return issues


def check_model_availability(config: Config):
    """Check that Whisper model can be loaded."""
    issues = []

    try:
        from faster_whisper import WhisperModel
        # Don't actually load, just check import
    except ImportError:
        issues.append("faster-whisper not installed")

    return issues


def main():
    """Run all validation checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate voice-journal configuration")
    parser.add_argument("--config", "-c", help="Path to config file")
    args = parser.parse_args()

    print("="*60)
    print("VOICE JOURNAL CONFIGURATION VALIDATOR")
    print("="*60)

    all_issues = []

    # Check dependencies
    print("\n[1/4] Checking dependencies...")
    missing = check_dependencies()

    if missing:
        print(f"  ❌ Missing dependencies:")
        for dep in missing:
            print(f"     - {dep}")
        all_issues.extend(missing)
    else:
        print("  ✓ All dependencies installed")

    # Check config
    print("\n[2/4] Validating configuration...")
    config, config_issues = check_config(args.config)

    if config_issues:
        print("  ❌ Config issues:")
        for issue in config_issues:
            print(f"     - {issue}")
        all_issues.extend(config_issues)
    else:
        print("  ✓ Configuration valid")
        print(f"     Model: {config.asr.model_size}")
        print(f"     Compute: {config.asr.compute_type}")
        print(f"     Batch (day): {config.scheduler.daytime_batch_hours}h")
        print(f"     Batch (night): {config.scheduler.overnight_batch_hours}h")

    # Check voice profiles
    print("\n[3/4] Checking voice profiles...")
    if config:
        profile_issues = check_voice_profiles(config)

        if profile_issues:
            print("  ❌ Voice profile issues:")
            for issue in profile_issues:
                print(f"     - {issue}")
            all_issues.extend(profile_issues)
        else:
            print("  ✓ Voice profiles found")
    else:
        print("  ⚠ Skipped (config invalid)")

    # Check model availability
    print("\n[4/4] Checking model availability...")
    if config:
        model_issues = check_model_availability(config)

        if model_issues:
            print("  ❌ Model issues:")
            for issue in model_issues:
                print(f"     - {issue}")
            all_issues.extend(model_issues)
        else:
            # Check if model downloaded
            model_size = config.asr.model_size
            print(f"  ✓ Model {model_size} available (will download on first run)")
    else:
        print("  ⚠ Skipped (config invalid)")

    # Summary
    print("\n" + "="*60)

    if all_issues:
        print("VALIDATION FAILED")
        print(f"Found {len(all_issues)} issue(s)")
        print("\nFix issues above and run again.")
        return 1
    else:
        print("VALIDATION PASSED")
        print("\nReady to start:")
        print("  python daemon_v2.py")
        return 0


if __name__ == "__main__":
    sys.exit(main())
