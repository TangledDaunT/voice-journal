"""
Data models for Hindi/Hinglish glossary.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Set


@dataclass
class CandidateTerm:
    """
    A candidate term extracted from conversations, pending validation.

    This represents a term that appears in transcripts and might be
    eligible for the glossary if it meets recurrence and significance criteria.
    """
    term_original: str  # Original form as it appears in transcript
    term_devanagari: str  # Devanagari form (if applicable)
    term_romanized: str  # Romanized form
    term_normalized: str  # Normalized form for matching

    # Occurrence tracking
    occurrence_count: int = 0
    conversation_ids: List[int] = field(default_factory=list)
    first_seen_date: date = None
    last_seen_date: date = None
    example_transcripts: List[str] = field(default_factory=list)

    # Set of unique days this term appeared
    unique_days: Set[str] = field(default_factory=set)

    def meets_recurrence_threshold(self, min_conversations: int = 3, min_days: int = 2) -> bool:
        """
        Check if term meets recurrence threshold for glossary consideration.

        Args:
            min_conversations: Minimum number of conversations
            min_days: Minimum number of unique days

        Returns:
            True if term appears frequently enough
        """
        return len(self.conversation_ids) >= min_conversations and len(self.unique_days) >= min_days

    def add_occurrence(self, conversation_id: int, date_str: str, example: str):
        """Add an occurrence of this term."""
        self.occurrence_count += 1
        self.conversation_ids.append(conversation_id)
        self.unique_days.add(date_str)

        # Track date range
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        if self.first_seen_date is None or date_obj < self.first_seen_date:
            self.first_seen_date = date_obj
        if self.last_seen_date is None or date_obj > self.last_seen_date:
            self.last_seen_date = date_obj

        # Store example (limit to top 3)
        if len(self.example_transcripts) < 3:
            self.example_transcripts.append(example)


@dataclass
class GlossaryTerm:
    """
    An approved term in the personal glossary.

    This represents a term that has been validated by the LLM as having
    personal/shared meaning between Shreyansh and Shivangi.
    """
    term_devanagari: str  # Devanagari form for display
    term_romanized: str  # Canonical Romanization for matching

    # Metadata
    first_seen_date: str  # ISO date string
    occurrence_count: int
    last_seen_date: str  # ISO date string

    # LLM-inferred content
    inferred_meaning: str  # LLM-generated meaning
    example_transcript: str  # Best example from transcripts

    # Tracking
    conversation_ids: List[int] = field(default_factory=list)
    is_validated: bool = False  # Human-validated

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            'term_devanagari': self.term_devanagari,
            'term_romanized': self.term_romanized,
            'first_seen_date': self.first_seen_date,
            'occurrence_count': self.occurrence_count,
            'last_seen_date': self.last_seen_date,
            'inferred_meaning': self.inferred_meaning,
            'example_transcript': self.example_transcript,
            'conversation_ids': self.conversation_ids,
            'is_validated': self.is_validated,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GlossaryTerm':
        """Create from dictionary."""
        return cls(
            term_devanagari=data['term_devanagari'],
            term_romanized=data['term_romanized'],
            first_seen_date=data['first_seen_date'],
            occurrence_count=data['occurrence_count'],
            last_seen_date=data['last_seen_date'],
            inferred_meaning=data['inferred_meaning'],
            example_transcript=data['example_transcript'],
            conversation_ids=data.get('conversation_ids', []),
            is_validated=data.get('is_validated', False),
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get('updated_at', datetime.now().isoformat())),
        )


@dataclass
class GlossaryEntry:
    """
    A single entry in the Obsidian Glossary.md file.

    Formatted for human readability in Obsidian.
    """
    term_devanagari: str
    term_romanized: str
    first_seen: str
    occurrences: int
    meaning: str
    example: str

    def to_markdown(self) -> str:
        """
        Generate Obsidian markdown format.

        Example output:
        ```markdown
        ## यार (Yaar)
        **Romanized:** yaar
        **First seen:** 2026-08-15
        **Occurrences:** 7
        **Meaning:** Affectionate term Shreyansh uses for Shivangi
        **Example:** "arey yaar, tu kab aa rahi hai?"
        ```
        """
        return f"""## {self.term_devanagari} ({self.term_romanized.title()})
**Romanized:** {self.term_romanized}
**First seen:** {self.first_seen}
**Occurrences:** {self.occurrences}
**Meaning:** {self.meaning}
**Example:** "{self.example}"

---
"""
