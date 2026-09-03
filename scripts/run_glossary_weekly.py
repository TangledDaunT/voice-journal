#!/usr/bin/env python3
"""
Weekly Glossary Pipeline.

Runs as a scheduled job (e.g., via systemd timer or cron) to:
1. Extract candidate terms from last 30 days of conversations
2. Filter by recurrence (3+ conversations across 2+ days)
3. Classify with LLM (personal/shared meaning vs common words)
4. Update glossary SQLite table
5. Generate Glossary.md for Obsidian

Usage:
    python scripts/run_glossary_weekly.py [--model MODEL] [--days DAYS]

Environment:
    VOICE_JOURNAL_DIR: Path to voice-journal directory (default: .)
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path
from typing import List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from glossary.extractor import extract_candidates, filter_by_recurrence, deduplicate_candidates
from glossary.classifier import classify_term, batch_classify
from glossary.models import GlossaryTerm, GlossaryEntry
from glossary.transliteration import is_common_hindi_word
from storage.database import SQLiteStore
from config.settings import Config
from utils.logger import logger, setup_logging


# SQL schema for glossary table
SCHEMA_GLOSSARY = """
CREATE TABLE IF NOT EXISTS glossary_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_devanagari TEXT NOT NULL,
    term_romanized TEXT NOT NULL UNIQUE,
    first_seen_date TEXT NOT NULL,
    occurrence_count INTEGER DEFAULT 1,
    last_seen_date TEXT NOT NULL,
    inferred_meaning TEXT,
    example_transcript TEXT,
    conversation_ids TEXT,  -- JSON array
    is_validated INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_glossary_romanized ON glossary_terms(term_romanized);
CREATE INDEX IF NOT EXISTS idx_glossary_first_seen ON glossary_terms(first_seen_date);
"""


class GlossaryManager:
    """Manages the glossary processing pipeline."""

    def __init__(self, config: Config):
        self.config = config
        self.db_path = Path(config.database.path)
        self.vault_path = Path(config.obsidian.vault_path)
        self.model = config.llm.model
        self.ollama_host = config.llm.ollama_host

        self._init_glossary_db()

    def _init_glossary_db(self):
        """Initialize glossary tables in database."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_GLOSSARY)
        conn.commit()
        conn.close()

    def load_existing_glossary(self) -> dict:
        """Load existing glossary terms from database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT term_romanized, occurrence_count FROM glossary_terms")
        rows = cursor.fetchall()
        conn.close()

        return {row['term_romanized']: row['occurrence_count'] for row in rows}

    def run_weekly_job(
        self,
        days: int = 30,
        min_conversations: int = 3,
        min_days: int = 2,
        batch_delay: float = 0.5
    ) -> dict:
        """
        Run the weekly glossary processing job.

        Args:
            days: Days to look back for candidate extraction
            min_conversations: Minimum conversations for recurrence threshold
            min_days: Minimum unique days for recurrence threshold
            batch_delay: Delay between LLM requests

        Returns:
            Statistics about the job
        """
        logger.info("="*60)
        logger.info("Starting Weekly Glossary Job")
        logger.info("="*60)

        start_time = datetime.now()

        # Step 1: Extract candidates
        logger.info(f"Step 1: Extracting candidates from last {days} days...")
        candidates = extract_candidates(str(self.db_path), days=days)
        logger.info(f"  Raw candidates: {len(candidates)}")

        # Step 2: Filter by recurrence
        logger.info(f"Step 2: Filtering by recurrence (min {min_conversations} convs, {min_days} days)...")
        recurrent_candidates = filter_by_recurrence(
            candidates,
            min_conversations=min_conversations,
            min_days=min_days
        )
        logger.info(f"  Recurrent candidates: {len(recurrent_candidates)}")

        # Step 3: Deduplicate
        logger.info("Step 3: Deduplicating...")
        deduped_candidates = deduplicate_candidates(recurrent_candidates)
        logger.info(f"  After deduplication: {len(deduped_candidates)}")

        # Step 4: Load existing glossary
        logger.info("Step 4: Loading existing glossary...")
        existing_terms = self.load_existing_glossary()
        logger.info(f"  Existing terms: {len(existing_terms)}")

        # Step 5: Filter out already-in-glossary terms
        new_candidates = [
            c for c in deduped_candidates
            if c.term_normalized not in existing_terms
        ]
        logger.info(f"  New candidates to classify: {len(new_candidates)}")

        if not new_candidates:
            logger.info("No new candidates to process.")
            stats = {
                'status': 'complete',
                'candidates_extracted': len(candidates),
                'candidates_recurrent': len(recurrent_candidates),
                'new_candidates': 0,
                'terms_added': 0,
                'terms_updated': 0,
                'duration_seconds': (datetime.now() - start_time).total_seconds()
            }
            return stats

        # Step 6: Classify with LLM
        logger.info(f"Step 5: Classifying {len(new_candidates)} candidates with {self.model}...")
        classifications = batch_classify(
            new_candidates,
            model=self.model,
            ollama_host=self.ollama_host,
            batch_delay=batch_delay
        )

        # Step 7: Add approved terms to glossary
        logger.info("Step 6: Adding approved terms to glossary...")
        terms_added = 0
        terms_updated = 0

        for candidate, classification in classifications:
            if classification and classification.get('should_include'):
                if self._add_to_glossary(candidate, classification):
                    terms_added += 1

        # Step 8: Update counts for existing terms
        logger.info("Step 7: Updating existing term counts...")
        for candidate in deduped_candidates:
            if candidate.term_normalized in existing_terms:
                self._update_term_count(candidate)
                terms_updated += 1

        # Step 9: Generate Glossary.md
        logger.info("Step 8: Generating Glossary.md...")
        self._generate_glossary_markdown()

        # Summary
        duration = (datetime.now() - start_time).total_seconds()
        logger.info("="*60)
        logger.info(f"Weekly Glossary Job Complete")
        logger.info(f"  Candidates extracted: {len(candidates)}")
        logger.info(f"  Recurrent candidates: {len(recurrent_candidates)}")
        logger.info(f"  New candidates classified: {len(new_candidates)}")
        logger.info(f"  Terms added: {terms_added}")
        logger.info(f"  Terms updated: {terms_updated}")
        logger.info(f"  Duration: {duration:.1f}s")
        logger.info("="*60)

        return {
            'status': 'complete',
            'candidates_extracted': len(candidates),
            'candidates_recurrent': len(recurrent_candidates),
            'new_candidates': len(new_candidates),
            'terms_added': terms_added,
            'terms_updated': terms_updated,
            'duration_seconds': duration
        }

    def _add_to_glossary(self, candidate, classification: dict) -> bool:
        """Add a term to the glossary."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Ensure we have a Devanagari form
            devanagari = candidate.term_devanagari if candidate.term_devanagari else candidate.term_original

            cursor.execute("""
                INSERT OR REPLACE INTO glossary_terms (
                    term_devanagari,
                    term_romanized,
                    first_seen_date,
                    occurrence_count,
                    last_seen_date,
                    inferred_meaning,
                    example_transcript,
                    conversation_ids,
                    is_validated,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
            """, (
                devanagari,
                candidate.term_romanized,
                str(candidate.first_seen_date),
                candidate.occurrence_count,
                str(candidate.last_seen_date),
                classification.get('inferred_meaning', ''),
                candidate.example_transcripts[0] if candidate.example_transcripts else '',
                json.dumps(candidate.conversation_ids)
            ))

            conn.commit()
            conn.close()

            logger.info(f"  ✓ Added: {devanagari} ({candidate.term_romanized})")
            return True

        except Exception as e:
            logger.error(f"  ✗ Failed to add {candidate.term_romanized}: {e}")
            return False

    def _update_term_count(self, candidate):
        """Update occurrence count for an existing term."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get existing data
            cursor.execute("""
                SELECT occurrence_count, conversation_ids
                FROM glossary_terms
                WHERE term_romanized = ?
            """, (candidate.term_romanized,))

            row = cursor.fetchone()
            if row:
                existing_count = row[0]
                existing_ids = set(json.loads(row[1]) if row[1] else [])

                # Merge conversation IDs
                new_ids = set(existing_ids) | set(candidate.conversation_ids)

                # Update
                cursor.execute("""
                    UPDATE glossary_terms
                    SET occurrence_count = ?,
                        conversation_ids = ?,
                        last_seen_date = ?,
                        updated_at = datetime('now')
                    WHERE term_romanized = ?
                """, (
                    existing_count + candidate.occurrence_count,
                    json.dumps(list(new_ids)),
                    str(candidate.last_seen_date),
                    candidate.term_romanized
                ))

                conn.commit()
                conn.close()

        except Exception as e:
            logger.error(f"Failed to update {candidate.term_romanized}: {e}")

    def _generate_glossary_markdown(self):
        """Generate Glossary.md for Obsidian."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM glossary_terms
            ORDER BY occurrence_count DESC, term_romanized ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return

        # Build markdown
        lines = [
            "# Shared Glossary\n",
            "Personal terms and shared shorthand from conversations with Shivangi.\n",
            "---\n"
        ]

        for row in rows:
            entry = GlossaryEntry(
                term_devanagari=row['term_devanagari'],
                term_romanized=row['term_romanized'],
                first_seen=row['first_seen_date'],
                occurrences=row['occurrence_count'],
                meaning=row['inferred_meaning'] or '(meaning not yet inferred)',
                example=row['example_transcript'] or '(no example available)'
            )
            lines.append(entry.to_markdown())

        # Write to file
        glossary_path = self.vault_path / "VoiceJournal" / "Glossary.md"
        glossary_path.parent.mkdir(parents=True, exist_ok=True)

        with open(glossary_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        logger.info(f"  Glossary.md updated: {len(rows)} terms")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Weekly Glossary Pipeline")
    parser.add_argument('--model', default='qwen2.5:1.5b', help='LLM model to use')
    parser.add_argument('--days', type=int, default=30, help='Days to look back')
    parser.add_argument('--config', '-c', help='Path to config file')
    parser.add_argument('--dry-run', action='store_true', help='Extract candidates only, no LLM calls')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level=log_level)

    # Load config
    if args.config:
        config = Config.from_yaml(args.config)
    else:
        config = Config()

    # Override model if specified
    if args.model:
        config.llm.model = args.model

    # Run job
    manager = GlossaryManager(config)

    if args.dry_run:
        # Dry run: extract candidates only
        candidates = extract_candidates(str(manager.db_path), days=args.days)
        recurrent = filter_by_recurrence(candidates)
        deduped = deduplicate_candidates(recurrent)

        print(f"\nDry Run Results:")
        print(f"  Raw candidates: {len(candidates)}")
        print(f"  Recurrent: {len(recurrent)}")
        print(f"  After dedup: {len(deduped)}")
        print(f"\nTop 10 candidates:")
        for i, c in enumerate(deduped[:10], 1):
            print(f"  {i}. {c.term_original} ({c.term_normalized}) - {c.occurrence_count}x")
    else:
        stats = manager.run_weekly_job(days=args.days)
        print(f"\nJob Complete:")
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
