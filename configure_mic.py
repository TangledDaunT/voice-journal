#!/usr/bin/env python3
"""
Configure external microphone for Voice Journal.
Run this on the laptop server after deployment.
"""

import sounddevice as sd
import json

def list_microphones():
    """List all available microphones."""
    print("\n" + "="*60)
    print("Available Microphones")
    print("="*60 + "\n")

    devices = sd.query_devices()
    input_devices = []

    for idx, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            input_devices.append({
                'index': idx,
                'name': dev['name'],
                'channels': dev['max_input_channels'],
                'sample_rate': dev['default_samplerate']
            })

            default_marker = " [DEFAULT]" if idx == sd.default.device[0] else ""
            print(f"[{idx:2d}] {dev['name']}{default_marker}")
            print(f"     Channels: {dev['max_input_channels']}, Sample Rate: {dev['default_samplerate']} Hz")
            print()

    return input_devices

def select_microphone():
    """Interactive microphone selection."""
    devices = list_microphones()

    if not devices:
        print("❌ No microphones found!")
        return None

    print("\n" + "="*60)
    print("Select your EXTERNAL MICROPHONE")
    print("="*60)
    print("\nEnter the device index number (e.g., 3, 5, etc.)")
    print("Or press Enter to use the default microphone")

    try:
        choice = input("\nMicrophone index: ").strip()

        if not choice:
            print("\n✓ Using default microphone")
            return None

        idx = int(choice)

        if 0 <= idx < len(sd.query_devices()):
            device = sd.query_devices(idx)
            print(f"\n✓ Selected: {device['name']}")
            print(f"  Channels: {device['max_input_channels']}")
            print(f"  Sample Rate: {device['default_samplerate']} Hz")
            return idx
        else:
            print("❌ Invalid device index")
            return None

    except ValueError:
        print("❌ Please enter a valid number")
        return None

def test_microphone(device_index=None):
    """Test microphone recording."""
    import numpy as np

    print("\n" + "="*60)
    print("Testing Microphone")
    print("="*60)

    duration = 3  # seconds
    sample_rate = 16000

    try:
        print(f"\nRecording for {duration} seconds...")
        print("🎤 SPEAK NOW!")

        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            device=device_index,
            dtype='float32'
        )

        sd.wait()

        # Check if we captured audio
        max_amplitude = np.max(np.abs(recording))
        print(f"\n✓ Recording complete")
        print(f"  Max amplitude: {max_amplitude:.4f}")

        if max_amplitude > 0.01:
            print("\n✅ Microphone is working!")
            return True
        else:
            print("\n⚠️  Very low audio levels")
            print("  Check if your microphone is muted or too far away")
            return False

    except Exception as e:
        print(f"\n❌ Recording failed: {e}")
        return False

def save_config(device_index):
    """Save microphone configuration."""
    config_path = "config/microphone_config.json"

    device_info = sd.query_devices(device_index)

    config = {
        'device_index': device_index,
        'device_name': device_info['name'],
        'sample_rate': 16000,
        'channels': 1
    }

    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"\n✓ Configuration saved to: {config_path}")

def main():
    print("\n" + "🎤"*30)
    print("VOICE JOURNAL - Microphone Configuration")
    print("🎤"*30)

    # Step 1: List microphones
    devices = list_microphones()

    # Step 2: Select microphone
    device_index = select_microphone()

    # Step 3: Test microphone
    print("\nStarting microphone test...")
    if test_microphone(device_index):
        # Step 4: Save configuration
        if device_index is not None:
            save_config(device_index)

        print("\n" + "="*60)
        print("✅ MICROPHONE CONFIGURED SUCCESSFULLY")
        print("="*60)
        print("\nThe daemon will use this microphone for audio capture.")
        print("\nTo start the daemon:")
        print("  python daemon.py")
        print()
    else:
        print("\n" + "="*60)
        print("⚠️  Microphone test failed")
        print("="*60)
        print("\nTroubleshooting:")
        print("  1. Check microphone connection")
        print("  2. Check system permissions (Sound preferences)")
        print("  3. Try a different device index")
        print("  4. Run again: python configure_mic.py")
        print()

if __name__ == "__main__":
    main()
