"""
LLM-based classification for glossary terms.

Determines if a candidate term should be added to the personal glossary
based on whether it has specific personal/shared meaning (not just common Hindi).
"""

import json
import time
import requests
from typing import Dict, Optional

from .models import CandidateTerm, GlossaryTerm
from .transliteration import is_common_hindi_word
from utils.logger import logger


# LLM classification prompt for Hindi/Hinglish slang detection
GLOSSARY_CLASSIFICATION_PROMPT = """You are analyzing a candidate slang/term from Hindi-English code-switched conversations.

CONTEXT: This is from a personal voice journal where Shreyansh records conversations with his girlfriend Shivangi and his own self-talk.

TERM (Original): {term_original}
TERM (Devanagari): {term_devanagari}
TERM (Romanized): {term_romanized}

OCCURRENCE DATA:
- Appeared {occurrence_count} times
- Across {conversation_count} conversations
- On {unique_days} separate days

EXAMPLE CONTEXTS:
{example_sentences}

---

Your task: Determine if this term should be added to a PERSONAL GLOSSARY.

EXCLUSION CRITERIA (reject if):
1. This is a common Hindi word known to ALL fluent Hindi speakers (e.g., "यार", "मतलब", "अच्छा", "आजा", "जा", "देख", "सुन", "बोल")
2. This is a generic term with no special personal meaning (e.g., generic nouns like "घर", "काम", "किताब")
3. Anyone fluent in Hindi would understand this without context
4. This is just a Romanized version of a common word

INCLUSION CRITERIA (accept only if one or more apply):
1. This is a NICKNAME or pet name used between Shreyansh and Shivangi
2. This is an INSIDE JOKE or private shorthand
3. The term has SPECIAL MEANING between them specifically (not general meaning)
4. This is a reference that an outsider wouldn't understand even if they speak Hindi fluently
5. This is a unique pronunciation or variation that they use

Think carefully: Would a random Hindi speaker understand what this means? If yes, REJECT.
Is this term part of a private language between Shreyansh and Shivangi? If yes, ACCEPT.

---

Return JSON in this exact format:
{{
  "should_include": true or false,
  "reason": "one-line explanation",
  "inferred_meaning": "if should_include=true, explain the personal/shared meaning in 1-2 sentences",
  "confidence": "high" or "medium" or "low"
}}

Return ONLY the JSON object, no other text."""


def classify_term(
    candidate: CandidateTerm,
    model: str = "qwen2.5:1.5b",
    ollama_host: str = "http://localhost:11434",
    timeout: int = 45
) -> Optional[Dict]:
    """
    Classify whether a candidate term belongs in the personal glossary.

    Uses an LLM to determine if the term has personal/shared meaning
    or is just a common Hindi word.

    Args:
        candidate: CandidateTerm to classify
        model: LLM model to use (default: qwen2.5:1.5b)
        ollama_host: Ollama server URL
        timeout: Request timeout in seconds

    Returns:
        Dictionary with classification result, or None on error
    """
    # Quick reject: common Hindi word
    if is_common_hindi_word(candidate.term_original):
        return {
            'should_include': False,
            'reason': 'Common Hindi word known to all speakers',
            'inferred_meaning': '',
            'confidence': 'high'
        }

    # Build prompt
    examples_text = "\n".join(
        f"{i+1}. \"{ex}\""
        for i, ex in enumerate(candidate.example_transcripts[:3])
    )

    prompt = GLOSSARY_CLASSIFICATION_PROMPT.format(
        term_original=candidate.term_original,
        term_devanagari=candidate.term_devanagari or "(N/A - Roman script)",
        term_romanized=candidate.term_romanized,
        occurrence_count=candidate.occurrence_count,
        conversation_count=len(candidate.conversation_ids),
        unique_days=len(candidate.unique_days),
        example_sentences=examples_text
    )

    try:
        # Call Ollama API
        response = requests.post(
            f"{ollama_host}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {
                    "temperature": 0.2,  # Lower temperature for classification
                    "num_predict": 300
                }
            },
            timeout=timeout
        )

        if response.status_code != 200:
            logger.error(f"LLM API error: {response.status_code}")
            return None

        result = response.json()
        content = result.get("message", {}).get("content", "")

        # Parse JSON from response
        classification = parse_llm_response(content)

        if classification:
            logger.info(
                f"Classified '{candidate.term_original}': "
                f"include={classification.get('should_include')}, "
                f"confidence={classification.get('confidence')}"
            )

        return classification

    except requests.Timeout:
        logger.error(f"LLM request timed out for term: {candidate.term_original}")
        return None

    except Exception as e:
        logger.error(f"LLM classification error: {e}")
        return None


def parse_llm_response(content: str) -> Optional[Dict]:
    """
    Parse JSON from LLM response.

    Args:
        content: Raw LLM response text

    Returns:
        Parsed dictionary or None
    """
    try:
        # Find JSON object in response
        start = content.find('{')
        end = content.rfind('}') + 1

        if start == -1 or end == 0:
            logger.warning(f"No JSON found in response: {content[:100]}")
            return None

        json_str = content[start:end]
        data = json.loads(json_str)

        # Validate required fields
        if 'should_include' not in data:
            data['should_include'] = False

        if 'reason' not in data:
            data['reason'] = 'No reason provided'

        if 'inferred_meaning' not in data:
            data['inferred_meaning'] = ''

        if 'confidence' not in data:
            data['confidence'] = 'medium'

        return data

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return None


def batch_classify(
    candidates: list,
    model: str = "qwen2.5:1.5b",
    ollama_host: str = "http://localhost:11434",
    batch_delay: float = 0.5
) -> list:
    """
    Classify multiple candidate terms.

    Args:
        candidates: List of CandidateTerm objects
        model: LLM model to use
        ollama_host: Ollama server URL
        batch_delay: Delay between requests (to avoid rate limit)

    Returns:
        List of (candidate, classification) tuples
    """
    results = []

    for i, candidate in enumerate(candidates, 1):
        logger.info(f"Classifying {i}/{len(candidates)}: {candidate.term_original}")

        classification = classify_term(
            candidate,
            model=model,
            ollama_host=ollama_host
        )

        results.append((candidate, classification))

        # Small delay between requests
        if i < len(candidates):
            time.sleep(batch_delay)

    return results


if __name__ == "__main__":
    # Test classification with sample data
    from .models import CandidateTerm
    from datetime import date

    # Create a test candidate
    test_candidate = CandidateTerm(
        term_original="बेटा",
        term_devanagari="बेटा",
        term_romanized="beta",
        term_normalized="beta",
        occurrence_count=5,
        conversation_ids=[1, 2, 3, 4, 5],
        first_seen_date=date(2026, 8, 15),
        last_seen_date=date(2026, 8, 31),
        example_transcripts=[
            "arey beta, tu kab aa rahi hai?",
            "beta ek kaam karna",
            "sun na beta ye baat"
        ]
    )
    test_candidate.unique_days = {'2026-08-15', '2026-08-20', '2026-08-25', '2026-08-28', '2026-08-31'}

    print(f"Testing classification for: {test_candidate.term_original}")
    print(f"Ollama host: http://localhost:11434")

    result = classify_term(test_candidate, model="qwen2.5:1.5b")

    if result:
        print("\nClassification Result:")
        print(json.dumps(result, indent=2))
    else:
        print("\nClassification failed. Is Ollama running?")
