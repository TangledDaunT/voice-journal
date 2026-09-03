"""
Stage 7: Obsidian Vault Output.
Creates and manages structured markdown notes for conversations.
"""

import os
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional
import yaml
from slugify import slugify

from config.settings import Config
from conversation.grouping import ConversationUnit
from llm_output.classifier import ClassificationResult
from utils.logger import logger, log_stage


@dataclass
class ConversationNote:
    """Data for a conversation note."""
    filepath: Path
    date: str
    start_time: str
    end_time: str
    duration_seconds: int
    participants: List[str]
    source_type: str
    is_shivangi_conversation: bool
    quality: str
    languages: List[str]
    summary: str
    transcript: str
    slug: str


@dataclass
class DailyNoteSummary:
    """Summary data for daily note."""
    date: str
    total_conversations: int
    with_shivangi: int
    self_talk: int
    media_flagged: int
    conversations: List[Dict]  # List of {link, preview}


class ObsidianWriter:
    """
    Stage 7: Writes conversation and daily notes to Obsidian vault.
    Maintains proper frontmatter and markdown formatting.
    """

    def __init__(self, config: Config):
        self.config = config
        self.vault_path = Path(config.obsidian.vault_path)
        self.daily_dir = Path(config.obsidian.daily_notes_dir)
        self.conversation_dir = Path(config.obsidian.conversation_notes_dir)

        # Create directory structure
        self._ensure_directories()

        # Track daily stats
        self._daily_stats: Dict[str, DailyNoteSummary] = {}

        logger.info(f"ObsidianWriter initialized: vault={self.vault_path}")

    def _ensure_directories(self):
        """Create necessary directories."""
        self.vault_path.mkdir(parents=True, exist_ok=True)
        (self.vault_path / self.daily_dir).mkdir(parents=True, exist_ok=True)

    def _create_slug(self, summary: str, max_length: int = 40) -> str:
        """Create a URL-safe slug from summary."""
        if not summary:
            return "conversation"

        # Use first part of summary before any punctuation
        text = summary.split('.')[0].split(',')[0].strip()
        slug = slugify(text, max_length=max_length)

        return slug if slug else "conversation"

    def write_conversation_note(
        self,
        conversation: ConversationUnit,
        classification: ClassificationResult,
        cleaned_transcript: Optional[str] = None
    ) -> Path:
        """
        Write a conversation note to the vault.

        Returns:
            Path to the created note
        """
        # Determine date and create date directory
        conv_date = conversation.start_time
        date_str = conv_date.strftime("%Y-%m-%d")
        date_dir = self.vault_path / self.conversation_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        # Generate slug and filename
        slug = self._create_slug(classification.summary)
        time_str = conv_date.strftime("%H%M")
        filename = f"{time_str}-{slug}.md"
        filepath = date_dir / filename

        # Build frontmatter
        participants = list(conversation.participants)
        languages = sorted(list(conversation.languages))
        duration = int(conversation.duration_seconds)

        frontmatter = {
            "date": date_str,
            "start_time": conv_date.strftime("%H:%M"),
            "end_time": conversation.end_time.strftime("%H:%M"),
            "duration_seconds": duration,
            "participants": participants,
            "source_type": classification.source_type,
            "is_shivangi_conversation": classification.is_shivangi_conversation,
            "quality": classification.quality,
            "languages": languages,
            "tags": ["voice-journal", "conversation"]
        }

        # Build note content
        content = self._format_conversation_note(
            frontmatter, classification, conversation, cleaned_transcript
        )

        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        log_stage("Obsidian", f"Wrote note: {filepath.name}")

        # Update daily note
        self._update_daily_note(
            date_str=date_str,
            conversation_path=filepath,
            preview=classification.summary[:100] if classification.summary else "",
            source_type=classification.source_type,
            is_shivangi=classification.is_shivangi_conversation
        )

        return filepath

    def _format_conversation_note(
        self,
        frontmatter: Dict,
        classification: ClassificationResult,
        conversation: ConversationUnit,
        cleaned_transcript: Optional[str] = None
    ) -> str:
        """Format the full markdown content for a conversation note."""
        # Check for low confidence segments
        has_low_confidence = any(
            getattr(seg, 'low_confidence', False)
            for seg in conversation.transcript_segments
        )

        # Add needs_review flag if any segment has low confidence
        if has_low_confidence:
            frontmatter["needs_review"] = True
            frontmatter["tags"].append("needs-review")

        # Build YAML frontmatter
        yaml_fm = "---\n" + yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True) + "---\n\n"

        # Build body
        body_parts = []

        # Summary
        summary_text = classification.summary if classification.summary else "*No summary available*"
        body_parts.append(f"## Summary\n\n{summary_text}\n")

        # Confidence note if present
        if classification.confidence_note:
            body_parts.append(f"> **Note:** {classification.confidence_note}\n")

        # Confidence warning if any segments are flagged
        if has_low_confidence:
            body_parts.append("> ⚠️ **Low confidence segments detected.** ")
            body_parts.append("Some transcript lines may need review. Flagged lines are marked with ⚠️\n")

        cleaned = cleaned_transcript or conversation.full_transcript
        cleaned_lines = cleaned.splitlines() or [cleaned]
        for index, seg in enumerate(conversation.transcript_segments):
            if getattr(seg, 'low_confidence', False):
                target = min(index, len(cleaned_lines) - 1)
                if "⚠️" not in cleaned_lines[target]:
                    cleaned_lines[target] += " ⚠️"

        body_parts.append("## Cleaned Transcript\n\n")
        body_parts.append("```transcript\n")
        body_parts.extend(f"{line}\n" for line in cleaned_lines)
        body_parts.append("```\n")

        body_parts.append("\n<details>\n<summary>Raw Transcript</summary>\n\n")
        body_parts.append("```transcript\n")
        body_parts.append(conversation.full_transcript + "\n")
        body_parts.append("```\n\n</details>\n")

        # Word count
        body_parts.append(f"\n---\n*{conversation.total_word_count} words, {int(conversation.duration_seconds)}s*")

        return yaml_fm + "".join(body_parts)

    def _update_daily_note(
        self,
        date_str: str,
        conversation_path: Path,
        preview: str,
        source_type: str,
        is_shivangi: bool
    ):
        """Update or create the daily note with new conversation link."""
        daily_path = self.vault_path / self.daily_dir / f"{date_str}.md"

        # Prepare conversation link
        rel_path = conversation_path.relative_to(self.vault_path.parent)
        # Format: [[path/to/conversation|display text]]
        link = f"[[Conversations/{date_str}/{conversation_path.stem}|{conversation_path.stem.split('-', 1)[0]}]]"
        one_liner = preview[:80] + ("..." if len(preview) > 80 else "")

        # Check if daily note exists
        if daily_path.exists():
            self._update_existing_daily_note(daily_path, link, one_liner, source_type, is_shivangi)
        else:
            self._create_daily_note(daily_path, date_str, link, one_liner, source_type, is_shivangi)

    def _create_daily_note(
        self,
        daily_path: Path,
        date_str: str,
        link: str,
        preview: str,
        source_type: str,
        is_shivangi: bool,
        total: int = 1
    ):
        """Create a new daily note."""
        frontmatter = {
            "date": date_str,
            "total_conversations": total,
            "with_shivangi": 1 if is_shivangi else 0,
            "self_talk": 1 if source_type == "self_talk" else 0,
            "media_flagged": 1 if source_type == "media_or_unknown" else 0,
            "tags": ["voice-journal", "daily"]
        }

        content = "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n\n"
        content += f"# Voice Journal: {date_str}\n\n"
        content += "## Summary\n\n"
        content += "*Daily summary will be updated as conversations are recorded.*\n\n"
        content += "## Conversations\n\n"
        content += f"- {link} — {preview}\n"

        with open(daily_path, 'w', encoding='utf-8') as f:
            f.write(content)

        log_stage("Obsidian", f"Created daily note: {daily_path.name}")

    def _update_existing_daily_note(
        self,
        daily_path: Path,
        link: str,
        preview: str,
        source_type: str,
        is_shivangi: bool
    ):
        """Update an existing daily note with new conversation."""
        with open(daily_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                fm_str = parts[1]
                body = parts[2]

                # Parse YAML
                try:
                    fm = yaml.safe_load(fm_str)
                except:
                    fm = {}

                # Update counters
                fm['total_conversations'] = fm.get('total_conversations', 0) + 1
                if is_shivangi:
                    fm['with_shivangi'] = fm.get('with_shivangi', 0) + 1
                if source_type == 'self_talk':
                    fm['self_talk'] = fm.get('self_talk', 0) + 1
                if source_type == 'media_or_unknown':
                    fm['media_flagged'] = fm.get('media_flagged', 0) + 1

                # Add conversation to body
                new_entry = f"- {link} — {preview}\n"

                # Find conversations section
                if "## Conversations" in body:
                    body = body.replace("## Conversations\n\n", f"## Conversations\n\n{new_entry}")
                else:
                    body += f"\n## Conversations\n\n{new_entry}"

                # Rewrite file
                new_content = "---\n" + yaml.dump(fm, default_flow_style=False) + "---\n" + body

                with open(daily_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                log_stage("Obsidian", f"Updated daily note: {daily_path.name}")

    def generate_daily_summary(self, date_str: str) -> str:
        """Generate a summary for a day's conversations."""
        # This would ideally call the LLM to summarize all conversations
        # For now, return a placeholder
        return f"Summary of conversations on {date_str}."


class DailyNoteUpdater:
    """
    Handles updates to daily notes when new conversations are added.
    Ensures idempotent updates without regeneration.
    """

    def __init__(self, config: Config):
        self.config = config
        self.vault_path = Path(config.obsidian.vault_path)
        self.daily_dir = Path(config.obsidian.daily_notes_dir)

    def get_summary(self, date_str: str) -> Optional[DailyNoteSummary]:
        """Get summary statistics for a day."""
        daily_path = self.vault_path / self.daily_dir / f"{date_str}.md"

        if not daily_path.exists():
            return None

        with open(daily_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    fm = yaml.safe_load(parts[1])
                    return DailyNoteSummary(
                        date=fm.get('date', date_str),
                        total_conversations=fm.get('total_conversations', 0),
                        with_shivangi=fm.get('with_shivangi', 0),
                        self_talk=fm.get('self_talk', 0),
                        media_flagged=fm.get('media_flagged', 0),
                        conversations=[]
                    )
                except:
                    pass

        return None


if __name__ == "__main__":
    # Quick test
    config = Config()
    config.obsidian.vault_path = "./test_vault"

    writer = ObsidianWriter(config)
    print(f"Vault path: {writer.vault_path}")
    print("ObsidianWriter ready")
