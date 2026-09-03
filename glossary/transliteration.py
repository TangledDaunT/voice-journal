"""
Devanagari to Roman transliteration for Hindi/Hinglish normalization.

Purpose: Normalize Devanagari script to canonical Roman form for term matching/deduplication.
The original Devanagari is preserved in the glossary display; this is purely for matching.

Example:
    "यार" and "yaar" and "yaar" (different transcriptions) → all normalize to "yaar"
    This allows detecting that they're the same term despite script differences.
"""

import re
from typing import Dict, Optional


# Common Hindi words that should NOT be added to glossary (known to all Hindi speakers)
COMMON_HINDI_WORDS = {
    # Extremely common everyday words
    'यार', 'yaar',  # friend/buddy
    'मतलब', 'matlab',  # meaning/i mean
    'अच्छा', 'accha', 'achha',  # good/okay
    'ठीक', 'theek',  # okay/fine
    'हाँ', 'haan',  # yes
    'नहीं', 'nahi', 'na',  # no
    'क्या', 'kya',  # what
    'कैसे', 'kaise',  # how
    'कब', 'kab',  # when
    'कहाँ', 'kahan',  # where
    'कौन', 'kaun',  # who
    'क्यों', 'kyun', 'kyon',  # why
    'कितना', 'kitna',  # how much
    'बहुत', 'bahut',  # very/much
    'थोड़ा', 'thoda',  # little
    'ज़रा', 'zara',  # a bit
    'अभी', 'abhi',  # now
    'फिर', 'phir',  # then/again
    'लेकिन', 'lekin', 'par',  # but
    'और', 'aur',  # and
    'या', 'ya',  # or
    'इसलिए', 'isliye',  # therefore
    'वाला', 'wala', 'vala',  # -wala suffix
    'वाली', 'wali', 'vali',  # -wali suffix
    'ज़रूर', 'zaroor',  # definitely
    'शायद', 'shayad',  # maybe
    'जल्दी', 'jaldi',  # quickly/soon
    'देर', 'der',  # late
    'समझ', 'samajh',  # understand
    'देख', 'dekh',  # see/look
    'सुन', 'sun',  # listen/hear
    'बोल', 'bol',  # speak/say
    'आजा', 'aaja',  # come
    'जा', 'ja',  # go
    'खा', 'kha',  # eat
    'पी', 'pi',  # drink
    'रहा', 'raha', 'raha',  # staying/continuous
    'रही', 'rahi',  # staying/continuous (fem)
    'है', 'hai',  # is
    'हैं', 'hain',  # are
    'था', 'tha',  # was
    'थी', 'thi',  # was (fem)
    'होगा', 'hoga',  # will be
    'होगी', 'hogi',  # will be (fem)
    'सकता', 'sakta',  # can
    'सकती', 'sakti',  # can (fem)
    'चाहिए', 'chahiye',  # should want
    'पता', 'pata',  # know/aware
    'नहीं', 'nahi',  # no
    'हाँ', 'haan',  # yes
    'ओके', 'oke', 'ok',  # okay
    'एक', 'ek',  # one
    'दो', 'do',  # two
    'तीन', 'teen',  # three
}


def normalize_to_roman(text: str) -> str:
    """
    Convert Devanagari script to IAST (International Alphabet of Sanskrit Transliteration).

    This provides a canonical Roman representation for matching purposes.

    Args:
        text: Text in Devanagari or Roman script

    Returns:
        Romanized text (IAST format)

    Example:
        >>> normalize_to_roman("यार")
        'yāra'
        >>> normalize_to_roman("बेटा")
        'beṭā'
    """
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate

        # Check if text contains Devanagari characters
        devanagari_pattern = re.compile(r'[ऀ-ॿ]+')
        if devanagari_pattern.search(text):
            # Transliterate Devanagari to IAST
            romanized = transliterate(text, sanscript.DEVANAGARI, sanscript.IAST)
            return romanized
        else:
            # Already in Roman script
            return text

    except ImportError:
        # Fallback: simple vowel mapping if indic-transliteration not available
        return _simple_transliterate(text)


def _simple_transliterate(text: str) -> str:
    """
    Fallback simple transliteration without indic-transliteration library.

    Uses common Devanagari to Roman mappings.
    """
    # Basic vowel mappings
    mappings = {
        'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ii', 'उ': 'u', 'ऊ': 'uu',
        'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au',
        'ं': 'n', 'ः': 'h', '्': '',  # Virama (suppresses inherent vowel)

        # Consonants
        'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
        'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
        'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
        'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
        'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
        'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v',
        'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h',

        # Matras (vowel signs)
        'ा': 'aa', 'ि': 'i', 'ी': 'ii', 'ु': 'u', 'ू': 'uu',
        'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au',
        'ृ': 'ri',
    }

    result = []
    i = 0
    while i < len(text):
        char = text[i]
        if char in mappings:
            result.append(mappings[char])
        elif 'ऀ' <= char <= 'ॿ':
            # Unknown Devanagari char, keep as-is
            result.append(char)
        else:
            # Non-Devanagari char, keep as-is
            result.append(char)
        i += 1

    return ''.join(result)


def normalize_for_matching(text: str) -> str:
    """
    Normalize text for term matching/deduplication.

    This produces a canonical form that allows matching of the same term
    across different transcriptions or script renderings.

    Steps:
    1. Transliterate Devanagari to Roman (IAST)
    2. Lowercase
    3. Remove common diacritical variations (ā→a, ī→i, etc.)
    4. Strip whitespace

    Args:
        text: Term to normalize

    Returns:
        Normalized term ready for matching

    Example:
        >>> normalize_for_matching("यार")
        'yar'
        >>> normalize_for_matching("yaar")
        'yar'
        >>> normalize_for_matching("Yāra")
        'yar'
    """
    # Step 1: Transliterate if needed
    romanized = normalize_to_roman(text)

    # Step 2: Lowercase
    normalized = romanized.lower().strip()

    # Step 3: Remove common diacritical variations
    # These are common transliteration variations that we want to normalize
    diacritic_mappings = {
        'ā': 'a',  # Long a
        'ī': 'i',  # Long i
        'ū': 'u',  # Long u
        'ṛ': 'ri',  # Vocalic r
        'ṇ': 'n',  # Retroflex n
        'ṭ': 't',  # Retroflex t
        'ḍ': 'd',  # Retroflex d
        'ṅ': 'n',  # Velar n
        'ñ': 'n',  # Palatal n
        'ś': 'sh',  # Palatal s
        'ṣ': 'sh',  # Retroflex s
        'ḥ': 'h',  # Visarga
    }

    for old, new in diacritic_mappings.items():
        normalized = normalized.replace(old, new)

    # Step 4: Remove extra whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def is_common_hindi_word(term: str) -> bool:
    """
    Check if a term is a common Hindi word that shouldn't be in glossary.

    Args:
        term: Term to check (can be in Devanagari or Roman)

    Returns:
        True if it's a common word known to all Hindi speakers
    """
    # Normalize for comparison
    normalized = normalize_for_matching(term)

    # Check against common words list
    # We check both the original and normalized forms
    return term.lower().strip() in COMMON_HINDI_WORDS or normalized in COMMON_HINDI_WORDS


def contains_devanagari(text: str) -> bool:
    """Check if text contains Devanagari characters."""
    devanagari_pattern = re.compile(r'[ऀ-ॿ]')
    return bool(devanagari_pattern.search(text))


def extract_potential_terms(text: str) -> list:
    """
    Extract potential Hindi/Hinglish terms from text.

    This is a heuristic approach to find candidate terms that might be
    slang, nicknames, or personal shorthand.

    Args:
        text: Transcript text

    Returns:
        List of potential terms (in original form, not normalized)
    """
    terms = []

    # Pattern 1: Words in Devanagari script
    devanagari_words = re.findall(r'[ऀ-ॿ]+', text)
    terms.extend(devanagari_words)

    # Pattern 2: Short words (2-6 chars) that might be slang
    # This catches Romanized Hindi like "yaar", "accha", "beta"
    short_words = re.findall(r'\b([a-z]{2,6})\b', text.lower())
    terms.extend(short_words)

    return terms


if __name__ == "__main__":
    # Test examples
    test_cases = [
        ("यार", "Term in Devanagari"),
        ("yaar", "Term in Roman"),
        ("बेटा", "Another Devanagari term"),
        ("beta", "Same term in Roman"),
        ("Yāra", "Term with diacritics"),
        ("छोटू", "Diminutive form"),
        ("chotu", "Romanized diminutive"),
    ]

    print("Transliteration Tests:")
    print("=" * 60)
    for original, description in test_cases:
        roman = normalize_to_roman(original)
        normalized = normalize_for_matching(original)
        is_common = is_common_hindi_word(original)

        print(f"\n{description}:")
        print(f"  Original:   {original}")
        print(f"  Romanized:  {roman}")
        print(f"  Normalized: {normalized}")
        print(f"  Is Common:  {is_common}")
