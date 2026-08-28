"""
Mute control utility for Voice Journal.
Provides simple CLI and file-based mute control.
"""

import os
import time
from pathlib import Path
from datetime import datetime
import argparse

from ..config.settings import Config


class MuteController:
    """
    Controls the mute state of the voice journal.
    Uses a file-based approach for cross-process communication.
    """

    def __init__(self, config: Config):
        self.config = config
        self.mute_file = Path(config.daemon.mute_file)
        self.mute_file.parent.mkdir(parents=True, exist_ok=True)

    def mute(self) -> bool:
        """Activate mute. Returns True if successful."""
        self.mute_file.touch()

        # Write timestamp
        with open(self.mute_file, 'w') as f:
            f.write(f"{datetime.now().isoformat()}\n")

        print("🔇 Voice Journal MUTED")
        self._notify("Voice Journal Muted", "Recording is paused")
        return True

    def unmute(self) -> bool:
        """Deactivate mute. Returns True if successful."""
        if self.mute_file.exists():
            self.mute_file.unlink()

        print("🔊 Voice Journal ACTIVE")
        self._notify("Voice Journal Active", "Recording resumed")
        return True

    def toggle(self) -> bool:
        """Toggle mute state. Returns True if now muted."""
        if self.is_muted():
            self.unmute()
            return False
        else:
            self.mute()
            return True

    def is_muted(self) -> bool:
        """Check if currently muted."""
        return self.mute_file.exists()

    def status(self) -> dict:
        """Get current mute status."""
        muted = self.is_muted()

        status = {
            'muted': muted,
            'state': 'PAUSED' if muted else 'RECORDING',
            'mute_file': str(self.mute_file)
        }

        if muted and self.mute_file.exists():
            try:
                with open(self.mute_file, 'r') as f:
                    timestamp = f.read().strip()
                    status['muted_since'] = timestamp
            except:
                pass

        return status

    def _notify(self, title: str, message: str):
        """Send desktop notification."""
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="Voice Journal",
                timeout=3
            )
        except ImportError:
            # plyer not available, skip notification
            pass
        except Exception as e:
            print(f"Notification failed: {e}")


def main():
    """CLI entry point for mute control."""
    parser = argparse.ArgumentParser(description="Voice Journal Mute Control")
    parser.add_argument(
        "action",
        choices=["mute", "unmute", "toggle", "status"],
        help="Action to perform"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to configuration file"
    )

    args = parser.parse_args()

    # Load config
    if args.config:
        config = Config.from_yaml(args.config)
    else:
        config = Config()

    controller = MuteController(config)

    # Execute action
    if args.action == "mute":
        controller.mute()

    elif args.action == "unmute":
        controller.unmute()

    elif args.action == "toggle":
        controller.toggle()

    elif args.action == "status":
        status = controller.status()
        print(f"\nVoice Journal Status:")
        print(f"  State: {status['state']}")
        print(f"  Mute File: {status['mute_file']}")
        if 'muted_since' in status:
            print(f"  Muted Since: {status['muted_since']}")
        print()


if __name__ == "__main__":
    main()
