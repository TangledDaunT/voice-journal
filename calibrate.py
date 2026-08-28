#!/usr/bin/env python3
"""
Voice Profile Calibration Script.
Records or loads audio samples and creates voice profiles.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from voice_journal.speaker_id.calibrate import calibrate_from_files, main as calibrate_main
from voice_journal.config.settings import Config


def find_calibration_files():
    """Look for default calibration files."""
    default_paths = [
        ("./calibration_shreyansh.m4a", "./calibration_shivangi.m4a"),
        ("./voice_journal/calibration_shreyansh.m4a", "./voice_journal/calibration_shivangi.m4a"),
        ("~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/20260828 160105.m4a",
         "~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/20260828 160310.m4a"),
    ]

    for shreyansh_path, shivangi_path in default_paths:
        shreyansh_expanded = Path(shreyansh_path).expanduser()
        shivangi_expanded = Path(shivangi_path).expanduser()

        if shreyansh_expanded.exists() and shivangi_expanded.exists():
            return str(shreyansh_expanded), str(shivangi_expanded)

    return None, None


def interactive_calibration():
    """Run interactive calibration with prompts."""
    print("\n" + "="*60)
    print("VOICE PROFILE CALIBRATION")
    print("="*60)
    print("""
This script will create voice profiles for speaker identification.
You need audio samples (30-60 seconds each) for:
  1. Shreyansh (your voice)
  2. Shivangi (your girlfriend's voice)

The profiles will be used to identify speakers in recordings.
""")

    # Check for existing calibration files
    print("Checking for existing calibration recordings...")
    shreyansh_path, shivangi_path = find_calibration_files()

    if shreyansh_path and shivangi_path:
        print(f"\n✓ Found calibration files:")
        print(f"  Shreyansh: {shreyansh_path}")
        print(f"  Shivangi: {shivangi_path}")

        response = input("\nUse these files? [Y/n]: ").strip().lower()
        if response != 'n':
            return calibrate_from_files(
                shreyansh_path=shreyansh_path,
                shivangi_path=shivangi_path,
                output_path="./config/voice_profiles.json"
            )

    # Prompt for file paths
    print("\nPlease provide paths to audio files:")
    shreyansh_path = input("  Shreyansh's voice file: ").strip()
    shivangi_path = input("  Shivangi's voice file: ").strip()

    # Expand user paths
    shreyansh_path = str(Path(shreyansh_path).expanduser())
    shivangi_path = str(Path(shivangi_path).expanduser())

    return calibrate_from_files(
        shreyansh_path=shreyansh_path,
        shivangi_path=shivangi_path,
        output_path="./config/voice_profiles.json"
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Calibrate voice profiles for speaker identification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use auto-detected Voice Memos recordings
  python calibrate.py

  # Specify custom files
  python calibrate.py --shreyansh ./my_voice.m4a --shivangi ./her_voice.m4a

  # Interactive mode
  python calibrate.py --interactive
        """
    )

    parser.add_argument(
        "--shreyansh",
        type=str,
        default="./calibration_shreyansh.m4a",
        help="Path to Shreyansh's voice sample (30-60 seconds)"
    )
    parser.add_argument(
        "--shivangi",
        type=str,
        default="./calibration_shivangi.m4a",
        help="Path to Shivangi's voice sample (30-60 seconds)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="./config/voice_profiles.json",
        help="Output path for voice profiles"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=2.0,
        help="Number of standard deviations for matching threshold"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode with prompts"
    )

    args = parser.parse_args()

    # Run in interactive mode if requested
    if args.interactive:
        profiles = interactive_calibration()
        return 0 if profiles else 1

    # Run calibration with provided arguments
    profiles = calibrate_from_files(
        shreyansh_path=args.shreyansh,
        shivangi_path=args.shivangi,
        output_path=args.output,
        threshold_multiplier=args.threshold
    )

    return 0 if profiles else 1


if __name__ == "__main__":
    sys.exit(main())
