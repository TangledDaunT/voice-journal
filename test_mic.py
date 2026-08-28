#!/usr/bin/env python3
"""
Microphone Testing Tool with Live Speaker Playback
Records from microphone and plays back through speakers in real-time
"""

import sys
import time
import numpy as np
import sounddevice as sd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def list_microphones():
    """List all available microphones."""
    print("\n" + "="*60)
    print("🎤 AVAILABLE MICROPHONES")
    print("="*60 + "\n")

    devices = sd.query_devices()
    input_devices = []

    for idx, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            input_devices.append({
                'index': idx,
                'name': dev['name'],
                'channels': dev['max_input_channels'],
                'sample_rate': int(dev['default_samplerate'])
            })

            default_marker = " [DEFAULT]" if idx == sd.default.device[0] else ""
            print(f"[{idx:2d}] {dev['name']}{default_marker}")
            print(f"     Channels: {dev['max_input_channels']}, Sample Rate: {int(dev['default_samplerate'])} Hz")
            print()

    return input_devices


def list_speakers():
    """List all available speakers/output devices."""
    print("\n" + "="*60)
    print("🔊 AVAILABLE SPEAKERS")
    print("="*60 + "\n")

    devices = sd.query_devices()
    output_devices = []

    for idx, dev in enumerate(devices):
        if dev['max_output_channels'] > 0:
            output_devices.append({
                'index': idx,
                'name': dev['name'],
                'channels': dev['max_output_channels'],
                'sample_rate': int(dev['default_samplerate'])
            })

            default_marker = " [DEFAULT]" if idx == sd.default.device[1] else ""
            print(f"[{idx:2d}] {dev['name']}{default_marker}")
            print(f"     Output Channels: {dev['max_output_channels']}, Sample Rate: {int(dev['default_samplerate'])} Hz")
            print()

    return output_devices


def test_mic_with_playback(input_device=None, output_device=None, duration=10, gain=1.0):
    """
    Test microphone with live playback through speakers.

    Args:
        input_device: Input device index (None = default)
        output_device: Output device index (None = default)
        duration: Test duration in seconds
        gain: Audio gain multiplier (default 1.0, increase if too quiet)
    """
    # Use 48000 Hz as default (more compatible) or 44100 Hz
    # Most devices support these sample rates
    sample_rate = 48000  # Changed from 16000 to 48000 for compatibility

    print("\n" + "="*60)
    print("🎤 MICROPHONE TEST WITH LIVE PLAYBACK")
    print("="*60)
    print(f"\nConfiguration:")
    print(f"  • Sample Rate: {sample_rate} Hz")
    print(f"  • Duration: {duration} seconds")
    print(f"  • Gain: {gain}x")

    # Get device info
    input_dev = sd.query_devices(input_device) if input_device is not None else sd.query_devices(kind='input')
    output_dev = sd.query_devices(output_device) if output_device is not None else sd.query_devices(kind='output')

    print(f"  • Input: {input_dev['name']}")
    print(f"  • Output: {output_dev['name']}")

    print("\n" + "="*60)
    print("🔴 RECORDING NOW - SPEAK INTO YOUR MICROPHONE!")
    print("🔊 You should hear your voice through speakers")
    print("="*60 + "\n")

    # Audio buffer
    audio_buffer = []

    def audio_callback(indata, outdata, frames, time_info, status):
        """Callback for simultaneous input/output."""
        if status:
            print(f"Status: {status}")

        # Apply gain to input
        processed = indata.copy() * gain

        # Store in buffer
        audio_buffer.append(processed.copy())

        # Output to speakers
        outdata[:] = processed

    try:
        # Create stream with both input and output
        with sd.Stream(
            device=(input_device, output_device),
            samplerate=sample_rate,
            channels=1,
            dtype='float32',
            callback=audio_callback,
            blocksize=512
        ):
            # Show countdown
            for i in range(duration, 0, -1):
                print(f"\r⏱️  Time remaining: {i:2d}s | Gain: {gain}x | Speak NOW!   ", end='', flush=True)
                time.sleep(1)

            print("\n\n✅ Recording complete!")

    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        return False

    # Combine buffer
    if audio_buffer:
        full_recording = np.concatenate(audio_buffer, axis=0)

        # Calculate statistics
        max_amplitude = np.max(np.abs(full_recording))
        avg_amplitude = np.mean(np.abs(full_recording))

        print(f"\n📊 Audio Statistics:")
        print(f"  • Max Amplitude: {max_amplitude:.4f}")
        print(f"  • Avg Amplitude: {avg_amplitude:.4f}")
        print(f"  • Total Samples: {len(full_recording)}")
        print(f"  • Duration: {len(full_recording)/sample_rate:.1f}s")

        if max_amplitude < 0.01:
            print("\n⚠️  WARNING: Very low audio levels detected!")
            print("  • Check if microphone is muted")
            print("  • Check microphone positioning")
            print("  • Try increasing gain: python test_mic.py --gain 2.0")
        elif max_amplitude > 0.9:
            print("\n⚠️  WARNING: Audio clipping detected!")
            print("  • Microphone may be too close")
            print("  • Try reducing gain: python test_mic.py --gain 0.5")
        else:
            print("\n✅ Audio levels look good!")

        return True

    return False


def interactive_test():
    """Interactive microphone testing."""
    print("\n" + "🎤"*30)
    print("MICROPHONE TESTING TOOL")
    print("🎤"*30)

    # List devices
    input_devices = list_microphones()
    output_devices = list_speakers()

    # Select input device
    print("\n" + "="*60)
    print("SELECT YOUR EXTERNAL MICROPHONE")
    print("="*60)
    print("\nEnter the device index number (or press Enter for default)")

    try:
        mic_choice = input("\nMicrophone index: ").strip()
        input_device = int(mic_choice) if mic_choice else None
    except ValueError:
        input_device = None

    # Select output device
    print("\n" + "="*60)
    print("SELECT YOUR SPEAKERS")
    print("="*60)
    print("\nEnter the device index number (or press Enter for default)")

    try:
        speaker_choice = input("\nSpeaker index: ").strip()
        output_device = int(speaker_choice) if speaker_choice else None
    except ValueError:
        output_device = None

    # Select gain
    print("\n" + "="*60)
    print("AUDIO GAIN")
    print("="*60)
    print("\nCurrent gain: 1.0x (normal)")
    print("If audio is too quiet, try: 2.0 or 3.0")
    print("If audio is too loud/distorted, try: 0.5")

    try:
        gain_input = input("\nGain (press Enter for 1.0): ").strip()
        gain = float(gain_input) if gain_input else 1.0
    except ValueError:
        gain = 1.0

    # Select duration
    print("\n" + "="*60)
    print("TEST DURATION")
    print("="*60)

    try:
        duration_input = input("\nDuration in seconds (press Enter for 10): ").strip()
        duration = int(duration_input) if duration_input else 10
    except ValueError:
        duration = 10

    # Run test
    success = test_mic_with_playback(
        input_device=input_device,
        output_device=output_device,
        duration=duration,
        gain=gain
    )

    if success:
        print("\n" + "="*60)
        print("✅ MIC TEST COMPLETE")
        print("="*60)
        print("\nYour microphone is working!")
        print("\nTo use this microphone for voice journal:")
        print(f"  export VOICE_JOURNAL_MIC={input_device if input_device is not None else 'default'}")
        print()
    else:
        print("\n" + "="*60)
        print("❌ MIC TEST FAILED")
        print("="*60)
        print("\nPlease check:")
        print("  1. Microphone is connected")
        print("  2. Correct device selected")
        print("  3. System permissions granted")
        print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test microphone with live playback")
    parser.add_argument('--input', '-i', type=int, help='Input device index')
    parser.add_argument('--output', '-o', type=int, help='Output device index')
    parser.add_argument('--duration', '-d', type=int, default=10, help='Test duration in seconds')
    parser.add_argument('--gain', '-g', type=float, default=1.0, help='Audio gain multiplier')
    parser.add_argument('--list', '-l', action='store_true', help='List devices only')
    parser.add_argument('--interactive', action='store_true', help='Interactive mode')

    args = parser.parse_args()

    if args.list:
        list_microphones()
        print()
        list_speakers()
    elif args.interactive or (args.input is None and args.output is None):
        interactive_test()
    else:
        test_mic_with_playback(
            input_device=args.input,
            output_device=args.output,
            duration=args.duration,
            gain=args.gain
        )


if __name__ == "__main__":
    main()
