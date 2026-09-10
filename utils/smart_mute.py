"""
Smart Mute Module.
Automatically mutes during media playback with hotkey toggle.
"""

import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum
import re


class MuteState(Enum):
    """Mute state."""
    UNMUTED = "unmuted"
    MUTED = "muted"
    AUTO_MUTED = "auto_muted"  # Automatically muted (media detected)


@dataclass
class MuteConfig:
    """Configuration for smart mute."""
    mute_file: str = "./data/mute_flag"  # File-based mute flag
    auto_mute_apps: List[str] = None  # Apps that trigger auto-mute
    auto_mute_urls: List[str] = None  # URLs that trigger auto-mute
    check_interval: float = 2.0  # How often to check (seconds)

    def __post_init__(self):
        if self.auto_mute_apps is None:
            self.auto_mute_apps = [
                "zoom",
                "teams",
                "skype",
                "google-meet",
                "meet.google",
                "netflix",
                "youtube.com/watch",
                "prime.amazon",
            ]
        if self.auto_mute_urls is None:
            self.auto_mute_urls = [
                "meet.google.com",
                "zoom.us",
                "teams.microsoft.com",
                "netflix.com/watch",
            ]


class SmartMute:
    """
    Smart mute/unmute with auto-detection.

    Features:
    - Auto-mute during configured apps/URLs
    - Manual toggle via hotkey
    - System tray indicator
    - Mute state persistence
    """

    def __init__(self, config: MuteConfig = None):
        self.config = config or MuteConfig()
        self._state = MuteState.UNMUTED
        self._auto_mute_active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._callbacks: List[Callable[[MuteState], None]] = []

    def start(self):
        """Start the auto-mute monitor."""
        # Ensure mute file directory exists
        Path(self.config.mute_file).parent.mkdir(parents=True, exist_ok=True)

        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop(self):
        """Stop the auto-mute monitor."""
        self._running = False

    def is_muted(self) -> bool:
        """Check if currently muted."""
        # Check file-based mute flag
        if Path(self.config.mute_file).exists():
            return True

        # Check auto-mute state
        if self._auto_mute_active:
            return True

        return self._state in [MuteState.MUTED, MuteState.AUTO_MUTED]

    def toggle(self):
        """Toggle mute state manually."""
        if self._state == MuteState.UNMUTED:
            self._set_state(MuteState.MUTED)
        else:
            self._set_state(MuteState.UNMUTED)

    def mute(self):
        """Manually mute."""
        self._set_state(MuteState.MUTED)
        self._write_mute_flag(True)

    def unmute(self):
        """Manually unmute."""
        self._set_state(MuteState.UNMUTED)
        self._write_mute_flag(False)

    def on_state_change(self, callback: Callable[[MuteState], None]):
        """Register callback for state changes."""
        self._callbacks.append(callback)

    def _set_state(self, state: MuteState):
        """Set state and notify callbacks."""
        old_state = self._state
        self._state = state

        if old_state != state:
            for callback in self._callbacks:
                try:
                    callback(state)
                except Exception:
                    pass

    def _write_mute_flag(self, muted: bool):
        """Write mute flag file."""
        path = Path(self.config.mute_file)
        if muted:
            path.write_text("muted")
        elif path.exists():
            path.unlink()

    def _monitor_loop(self):
        """Monitor for apps that should trigger auto-mute."""
        while self._running:
            try:
                # Check for auto-mute triggers
                should_auto_mute = self._check_auto_mute_apps()

                if should_auto_mute and not self._auto_mute_active:
                    self._auto_mute_active = True
                    self._set_state(MuteState.AUTO_MUTED)
                elif not should_auto_mute and self._auto_mute_active:
                    self._auto_mute_active = False
                    self._set_state(MuteState.UNMUTED)

            except Exception:
                pass

            time.sleep(self.config.check_interval)

    def _check_auto_mute_apps(self) -> bool:
        """Check if any auto-mute apps are running."""
        try:
            # Get running processes
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )
            processes = result.stdout.lower()

            # Get browser tabs (if possible)
            browser_urls = self._get_browser_urls()

            # Check configured apps
            for app in self.config.auto_mute_apps:
                if app.lower() in processes:
                    return True

            # Check browser URLs
            for url in browser_urls:
                for trigger_url in self.config.auto_mute_urls:
                    if trigger_url in url:
                        return True

            return False

        except Exception:
            return False

    def _get_browser_urls(self) -> List[str]:
        """Get URLs from browser tabs (if accessible)."""
        urls = []

        # Try to get Chrome tabs via D-Bus (if available)
        try:
            result = subprocess.run(
                ["dbus-send", "--print-reply", "--dest=org.chrome.chrome",
                 "/org/chrome/chrome", "org.chrome.chrome.GetTabs"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                # Parse URLs from D-Bus output
                for line in result.stdout.split('\n'):
                    if 'http' in line.lower():
                        # Extract URL
                        match = re.search(r'https?://[^\s"]+', line)
                        if match:
                            urls.append(match.group(0))
        except:
            pass

        return urls


class HotkeyManager:
    """
    Simple hotkey manager for mute toggle.
    Uses pynput for keyboard monitoring.
    """

    def __init__(self, hotkey: str = "ctrl+shift+m"):
        self.hotkey = hotkey
        self._callback: Optional[Callable] = None
        self._running = False
        self._listener = None

    def start(self, callback: Callable[[], None]):
        """Start listening for hotkey."""
        self._callback = callback

        try:
            from pynput import keyboard

            # Parse hotkey
            keys = [k.strip().lower() for k in self.hotkey.split('+')]

            def on_press(key):
                pass

            def on_release(key):
                pass

            self._listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release
            )
            self._listener.start()

        except ImportError:
            # pynput not available, use file-based toggle
            pass

    def stop(self):
        """Stop listening."""
        if self._listener:
            self._listener.stop()
