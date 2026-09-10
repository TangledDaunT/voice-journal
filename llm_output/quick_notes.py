"""
Quick Journal Notes Module.
Voice command detection and instant note creation.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Callable
from dataclasses import dataclass
import threading
import queue
import time


@dataclass
class QuickNote:
    """A quick note created via voice command."""
    text: str
    timestamp: datetime
    conversation_id: Optional[str] = None
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class QuickNoteDetector:
    """
    Detects voice commands for quick notes.

    Supported commands:
    - "Note: <text>" - Creates instant note
    - "Reminder: <text>" - Creates reminder note
    - "Todo: <text>" - Creates todo note
    """

    # Voice patterns for note commands
    NOTE_PATTERNS = [
        r"^note[:\s]+(.+)$",
        r"^quick note[:\s]+(.+)$",
        r"^add note[:\s]+(.+)$",
    ]

    REMINDER_PATTERNS = [
        r"^reminder[:\s]+(.+)$",
        r"^remind me (?:to )?(.+)$",
    ]

    TODO_PATTERNS = [
        r"^todo[:\s]+(.+)$",
        r"^to.do[:\s]+(.+)$",
        r"^add (?:a )?todo[:\s]+(.+)$",
    ]

    def __init__(self, config=None):
        self.config = config
        self._note_callbacks: List[Callable[[QuickNote], None]] = []

    def detect_and_extract(self, transcript: str) -> Optional[QuickNote]:
        """
        Check if transcript contains a note command.

        Args:
            transcript: The transcription text

        Returns:
            QuickNote if detected, None otherwise
        """
        text = transcript.strip().lower()

        # Check for note patterns
        for pattern in self.NOTE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                note_text = match.group(1).strip()
                return QuickNote(
                    text=note_text,
                    timestamp=datetime.now(),
                    tags=["note"]
                )

        # Check for reminder patterns
        for pattern in self.REMINDER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                note_text = match.group(1).strip()
                return QuickNote(
                    text=note_text,
                    timestamp=datetime.now(),
                    tags=["reminder"]
                )

        # Check for todo patterns
        for pattern in self.TODO_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                note_text = match.group(1).strip()
                return QuickNote(
                    text=note_text,
                    timestamp=datetime.now(),
                    tags=["todo"]
                )

        return None

    def on_note_detected(self, callback: Callable[[QuickNote], None]):
        """Register callback for when a note is detected."""
        self._note_callbacks.append(callback)

    def process_transcript(self, transcript: str) -> bool:
        """
        Process a transcript and create note if command detected.

        Args:
            transcript: The transcription text

        Returns:
            True if note was created, False otherwise
        """
        note = self.detect_and_extract(transcript)
        if note:
            for callback in self._note_callbacks:
                try:
                    callback(note)
                except Exception:
                    pass
            return True
        return False


class QuickNoteWriter:
    """
    Writes quick notes to files.
    """

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.notes_dir = vault_path / "QuickNotes"
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def write_note(self, note: QuickNote) -> Path:
        """
        Write a quick note to a file.

        Args:
            note: The note to write

        Returns:
            Path to the created note file
        """
        # Generate filename
        timestamp_str = note.timestamp.strftime("%Y%m%d_%H%M%S")
        tag_str = "-".join(note.tags) if note.tags else "note"
        filename = f"{timestamp_str}_{tag_str}.md"
        filepath = self.notes_dir / filename

        # Format note content
        content = self._format_note(note)

        # Write
        filepath.write_text(content)

        return filepath

    def _format_note(self, note: QuickNote) -> str:
        """Format note as markdown."""
        lines = [
            f"# {note.text}",
            "",
            f"**Created:** {note.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]

        if note.tags:
            lines.append(f"**Tags:** {', '.join(note.tags)}")
            lines.append("")

        if note.conversation_id:
            lines.append(f"**Conversation:** [[{note.conversation_id}]]")
            lines.append("")

        return "\n".join(lines)


class KeyboardShortcutListener:
    """
    Listen for keyboard shortcuts to create manual notes.

    Shortcuts:
    - Ctrl+Shift+N: Create new note
    - Ctrl+Shift+T: Create todo note
    """

    def __init__(self, callback: Callable[[str, List[str]], None]):
        """
        Initialize keyboard listener.

        Args:
            callback: Called with (note_text, tags) when shortcut pressed
        """
        self.callback = callback
        self._running = False
        self._listener = None

    def start(self):
        """Start listening for shortcuts."""
        try:
            from pynput import keyboard

            def on_activate_new_note():
                # Open dialog or use clipboard
                self.callback("", ["manual"])

            def on_activate_todo():
                self.callback("", ["todo", "manual"])

            # Register hotkeys
            self._listener = keyboard.GlobalHotKeys({
                '<ctrl>+<shift>+n': on_activate_new_note,
                '<ctrl>+<shift>+t': on_activate_todo,
            })
            self._listener.start()
            self._running = True

        except ImportError:
            pass

    def stop(self):
        """Stop listening."""
        if self._listener:
            self._listener.stop()
        self._running = False


def create_quick_note_text():
    """
    Helper function to get note text from clipboard or prompt.
    Can be called from keyboard shortcut.
    """
    try:
        import pyperclip
        text = pyperclip.paste()
        if text:
            return text.strip()
    except:
        pass

    return ""
