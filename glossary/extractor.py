"""
Candidate term extraction from conversation transcripts.
"""

import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set

from .models import CandidateTerm
from .transliteration import (
    normalize_to_roman,
    normalize_for_matching,
    is_common_hindi_word,
    contains_devanagari,
    extract_potential_terms,
)


def is_valid_term(term: str) -> bool:
    """
    Filter out invalid terms (ASR glitches, noise, etc).

    Rejects:
    - Terms with 3+ repeated characters (ASR glitch)
    - Terms shorter than 2 chars
    - Single-letter terms
    """
    if len(term) < 2:
        return False

    # Reject if same character repeated 3+ times in a row
    import re
    if re.search(r'(.)\1{2,}', term):
        return False

    # Reject if 50%+ of characters are the same (repetition noise)
    char_counts = {}
    for char in term:
        char_counts[char] = char_counts.get(char, 0) + 1

    max_count = max(char_counts.values())
    if max_count > len(term) * 0.5:
        return False

    return True


def extract_candidates(
    db_path: str,
    days: int = 30,
    min_term_length: int = 2,
    min_occurrences: int = 2
) -> List[CandidateTerm]:
    """
    Extract candidate glossary terms from recent conversations.

    This is the first stage of the glossary pipeline. It finds potential
    terms by scanning transcripts and filtering by basic criteria.

    Args:
        db_path: Path to SQLite database
        days: Number of days to look back (default: 30)
        min_term_length: Minimum term length in characters
        min_occurrences: Minimum occurrences to consider

    Returns:
        List of CandidateTerm objects
    """
    # Query database for recent conversations
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            conversation_id,
            date,
            transcript,
            summary
        FROM conversations
        WHERE date >= ?
        AND source_type IN ('live_conversation', 'self_talk')
        ORDER BY date DESC
    """, (start_date,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    # Build term occurrence map
    term_occurrences = defaultdict(lambda: CandidateTerm(
        term_original="",
        term_devanagari="",
        term_romanized="",
        term_normalized=""
    ))

    for row in rows:
        conversation_id = row['conversation_id']
        date_str = row['date']
        transcript = row['transcript'] or ""

        # Extract potential terms
        potential_terms = extract_potential_terms(transcript)

        for term in potential_terms:
            # Skip if too short
            if len(term) < min_term_length:
                continue

            # Skip ASR glitches and noise
            if not is_valid_term(term):
                continue

            # Normalize for matching
            normalized = normalize_for_matching(term)

            # Skip common Hindi words
            if is_common_hindi_word(term):
                continue

            # Determine Devanagari and Romanized forms
            if contains_devanagari(term):
                devanagari = term
                romanized = normalize_to_roman(term)
            else:
                # Term is already in Roman script
                devanagari = ""  # Will be filled later if we find Devanagari version
                romanized = term

            # Build example context (surrounding text)
            example = extract_context(transcript, term)

            # Update occurrence tracking
            if normalized not in term_occurrences:
                term_occurrences[normalized].term_original = term
                term_occurrences[normalized].term_devanagari = devanagari
                term_occurrences[normalized].term_romanized = romanized
                term_occurrences[normalized].term_normalized = normalized

            term_occurrences[normalized].add_occurrence(
                conversation_id=conversation_id,
                date_str=date_str,
                example=example
            )

    # Filter by minimum occurrences
    candidates = [
        term for term in term_occurrences.values()
        if term.occurrence_count >= min_occurrences
    ]

    # Sort by occurrence count (descending)
    candidates.sort(key=lambda t: t.occurrence_count, reverse=True)

    return candidates


def extract_context(transcript: str, term: str, context_length: int = 50) -> str:
    """
    Extract context surrounding a term occurrence.

    Args:
        transcript: Full transcript text
        term: Term to find
        context_length: Characters of context on each side

    Returns:
        Context string with term highlighted
    """
    # Case-insensitive search
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    match = pattern.search(transcript)

    if not match:
        return ""

    start = max(0, match.start() - context_length)
    end = min(len(transcript), match.end() + context_length)

    # Extract context
    context = transcript[start:end]

    # Clean up (remove partial words at boundaries)
    if start > 0:
        context = context[context.find(' ') + 1:]
    if end < len(transcript):
        context = context[:context.rfind(' ')]

    return context.strip()


def filter_by_recurrence(
    candidates: List[CandidateTerm],
    min_conversations: int = 3,
    min_days: int = 2
) -> List[CandidateTerm]:
    """
    Filter candidates by recurrence threshold.

    This ensures terms only make it to the glossary if they appear
    across multiple distinct conversations on multiple days.

    Args:
        candidates: List of candidate terms
        min_conversations: Minimum number of conversations
        min_days: Minimum number of unique days

    Returns:
        Filtered list of candidates
    """
    return [
        c for c in candidates
        if c.meets_recurrence_threshold(min_conversations, min_days)
    ]


def deduplicate_candidates(candidates: List[CandidateTerm]) -> List[CandidateTerm]:
    """
    Remove duplicate candidates based on normalized form.

    This handles cases where the same term appears in both
    Devanagari and Roman script.
    """
    seen_normalized = {}

    for candidate in candidates:
        norm = candidate.term_normalized

        if norm in seen_normalized:
            # Merge conversation IDs and examples
            existing = seen_normalized[norm]
            existing.conversation_ids.extend(candidate.conversation_ids)
            existing.unique_days.update(candidate.unique_days)
            existing.occurrence_count += candidate.occurrence_count

            # Prefer Devanagari form if available
            if candidate.term_devanagari and not existing.term_devanagari:
                existing.term_devanagari = candidate.term_devanagari
        else:
            seen_normalized[norm] = candidate

    return list(seen_normalized.values())


if __name__ == "__main__":
    # Test extraction with sample data
    import os

    # This would normally come from config
    db_path = os.path.expanduser("~/Documents/sound_transcribe/voice-journal/data/voice_journal.db")

    if Path(db_path).exists():
        print(f"Extracting candidates from {db_path}...")
        candidates = extract_candidates(db_path, days=30)

        print(f"\nFound {len(candidates)} candidate terms:")
        for i, c in enumerate(candidates[:10], 1):
            print(f"\n{i}. {c.term_original}")
            print(f"   Normalized: {c.term_normalized}")
            print(f"   Occurrences: {c.occurrence_count}")
            print(f"   Days: {len(c.unique_days)}")
            print(f"   Example: {c.example_transcripts[0][:50]}...")
    else:
        print(f"Database not found at {db_path}")
        print("Run the voice journal daemon first to populate conversations.")
