#!/usr/bin/env python3
"""
Test script for Hindi glossary pipeline.

Tests:
1. Transliteration normalization
2. Candidate extraction
3. LLM classification
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from glossary.transliteration import (
    normalize_to_roman,
    normalize_for_matching,
    is_common_hindi_word,
    contains_devanagari,
)
from glossary.models import CandidateTerm
from glossary.classifier import classify_term
from datetime import date


def test_transliteration():
    """Test Devanagari to Roman transliteration."""
    print("\n" + "="*60)
    print("Test: Transliteration")
    print("="*60)

    test_cases = [
        ("यार", "Common slang 'yaar'"),
        ("बेटा", "Affectionate term 'beta'"),
        ("छोटू", "Diminutive 'chotu'"),
        ("मतलब", "Common word 'matlab'"),
        ("yaar", "Romanized 'yaar'"),
        ("beta", "Romanized 'beta'"),
    ]

    all_passed = True

    for original, description in test_cases:
        try:
            roman = normalize_to_roman(original)
            normalized = normalize_for_matching(original)
            is_common = is_common_hindi_word(original)

            print(f"\n{description}:")
            print(f"  Original:    {original}")
            print(f"  Roman:      {roman}")
            print(f"  Normalized: {normalized}")
            print(f"  Is Common:  {is_common}")

        except Exception as e:
            print(f"\n✗ FAILED: {description}")
            print(f"  Error: {e}")
            all_passed = False

    if all_passed:
        print("\n✓ All transliteration tests passed")
    else:
        print("\n✗ Some tests failed")

    return all_passed


def test_common_words():
    """Test common Hindi word detection."""
    print("\n" + "="*60)
    print("Test: Common Hindi Word Detection")
    print("="*60)

    common_words = ["यार", "yaar", "मतलब", "matlab", "अच्छा", "accha"]
    uncommon_words = ["बेटा", "beta", "छोटू", "chotu"]

    all_passed = True

    print("\nShould be detected as common:")
    for word in common_words:
        is_common = is_common_hindi_word(word)
        status = "✓" if is_common else "✗"
        print(f"  {status} {word}: {is_common}")
        if not is_common:
            all_passed = False

    print("\nShould NOT be detected as common:")
    for word in uncommon_words:
        is_common = is_common_hindi_word(word)
        status = "✓" if not is_common else "✗"
        print(f"  {status} {word}: {is_common}")
        if is_common:
            all_passed = False

    return all_passed


def test_llm_classification():
    """Test LLM classification (requires Ollama running)."""
    print("\n" + "="*60)
    print("Test: LLM Classification")
    print("="*60)

    # Check if Ollama is available
    import requests
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code != 200:
            print("\n✗ Ollama not available at localhost:11434")
            return False
    except:
        print("\n✗ Cannot connect to Ollama. Is it running?")
        print("  Start with: ollama serve")
        return False

    # Create test candidate (this should be rejected - it's common)
    test_candidate = CandidateTerm(
        term_original="यार",
        term_devanagari="यार",
        term_romanized="yaar",
        term_normalized="yaar",
        occurrence_count=5,
        conversation_ids=[1, 2, 3, 4, 5],
        first_seen_date=date(2026, 8, 15),
        last_seen_date=date(2026, 8, 31),
        example_transcripts=[
            "arey yaar, tu kab aa rahi hai?",
            "yaar ek kaam karna",
            "sun na yaar ye baat"
        ]
    )
    test_candidate.unique_days = {'2026-08-15', '2026-08-20', '2026-08-25'}

    print(f"\nClassifying: {test_candidate.term_original}")
    print(f"  Model: qwen2.5:1.5b")

    try:
        result = classify_term(
            test_candidate,
            model="qwen2.5:1.5b",
            ollama_host="http://localhost:11434"
        )

        if result:
            print(f"\nResult:")
            print(f"  Should Include: {result.get('should_include')}")
            print(f"  Reason: {result.get('reason')}")
            print(f"  Confidence: {result.get('confidence')}")

            # Test assertion: common word should be rejected
            if not result.get('should_include'):
                print("\n✓ Correctly rejected common word")
                return True
            else:
                print("\n✗ Failed: Should have rejected common word 'yaar'")
                return False
        else:
            print("\n✗ No result returned from LLM")
            return False

    except Exception as e:
        print(f"\n✗ Classification error: {e}")
        return False


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("Hindi Glossary Pipeline Tests")
    print("="*60)

    results = {
        'transliteration': test_transliteration(),
        'common_words': test_common_words(),
        'llm_classification': test_llm_classification(),
    }

    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")

    all_passed = all(results.values())
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed."))
    print("="*60)

    return all_passed


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Hindi glossary pipeline")
    parser.add_argument('--skip-llm', action='store_true', help='Skip LLM tests')
    args = parser.parse_args()

    if args.skip_llm:
        # Run only non-LLM tests
        results = {
            'transliteration': test_transliteration(),
            'common_words': test_common_words(),
        }

        print("\n" + "="*60)
        print("Test Summary (LLM skipped)")
        print("="*60)
        for test_name, passed in results.items():
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status}: {test_name}")

        all_passed = all(results.values())
    else:
        all_passed = run_all_tests()

    sys.exit(0 if all_passed else 1)
