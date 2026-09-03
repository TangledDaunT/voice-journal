"""
Hindi/Hinglish Glossary Module.

Extracts recurring slang and personal shorthand from code-switched conversations.
Runs as a weekly batch job, not per-conversation.
"""

from .transliteration import normalize_to_roman, normalize_for_matching
from .models import GlossaryTerm, CandidateTerm
from .extractor import extract_candidates
from .classifier import classify_term

__all__ = [
    'normalize_to_roman',
    'normalize_for_matching',
    'GlossaryTerm',
    'CandidateTerm',
    'extract_candidates',
    'classify_term',
]
