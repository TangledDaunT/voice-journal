#!/usr/bin/env python3
"""
eval/normalize.py

Text normalization for Hinglish evaluation.
- NFC normalize, lowercase, strip punctuation, collapse whitespace
- Transliterate Devanagari to Roman (deterministic)
- Normalize common number forms
- Apply spelling variants from eval/variants.yaml (canonical forms)
- Same normalizer applied to reference and hypothesis
"""

import sys
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set
import yaml

# Add parent for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate
    INDIC_AVAILABLE = True
except ImportError:
    INDIC_AVAILABLE = False
    print("⚠️ indic-transliteration not available, Devanagari transliteration disabled", file=sys.stderr)


# ============================
# Variant Mapping (from eval/variants.yaml)
# ============================
DEFAULT_VARIANTS = {
    # Hindi common variants
    "hai": ["hain", "hae", "ha"],
    "nahi": ["nahin", "nahi", "nahiin", "naheen"],
    "ho": ["hoo", "hoo"],
    "ka": ["kaa", "ka"],
    "ki": ["kee", "ki"],
    "se": ["say", "se"],
    "mein": ["me", "main", "mein"],
    "aur": ["or", "aur"],
    "kya": ["kia", "kya"],
    "ke": ["kay", "ke"],
    "ko": ["ko", "ko"],
    "bhi": ["bhee", "bhi"],
    "ye": ["yeh", "ye"],
    "wo": ["woh", "wo"],
    "tha": ["thaa", "tha"],
    "thi": ["thee", "thi"],
    "the": ["thee", "the"],
    "kar": ["kr", "kar"],
    "karna": ["krna", "karna"],
    "hai": ["hai", "hain"],
    "hum": ["hm", "hum"],
    "tum": ["tm", "tum"],
    "mera": ["mera", "meraa"],
    "tera": ["tera", "teraa"],
    "uska": ["uska", "uskaa"],
    "iska": ["iska", "iskaa"],
    "kya": ["kya", "kia"],
    "kyun": ["kyu", "kyun", "q"],
    "kaise": ["kaise", "kesay"],
    "kahan": ["kahan", "kha"],
    "kab": ["kb", "kab"],
    "kon": ["kaun", "kon"],
    "kitna": ["kitna", "ktna"],
    "accha": ["achha", "acha", "accha", "acchaa"],
    "theek": ["thik", "theek", "thk"],
    "bas": ["bs", "bas"],
    "abhi": ["abi", "abhi"],
    "pehle": ["pehle", "phle"],
    "baad": ["bad", "baad", "baadmein"],
    "kal": ["kl", "kal"],
    "aaj": ["aj", "aaj"],
    "subah": ["subha", "subah"],
    "shaam": ["sham", "shaam"],
    "raat": ["rat", "raat"],
    "din": ["dn", "din"],
    "hafta": ["hfta", "hafta"],
    "mahina": ["mhina", "mahina", "mahena"],
    "saal": ["sal", "saal"],
    "ghar": ["ghr", "ghar"],
    "office": ["ofis", "office", "offis"],
    "meeting": ["miting", "meeting", "mitng"],
    "call": ["cl", "call"],
    "message": ["msg", "mesg", "message"],
    "docker": ["dokar", "docker"],
    "tailscale": ["telskel", "tailscale", "tailscal"],
    "deployment": ["deploi", "deployment", "deploy"],
    "server": ["sarvar", "server"],
    "database": ["databes", "database", "db"],
    "config": ["confg", "config", "cnfg"],
    "script": ["skript", "script"],
    "code": ["kod", "code"],
    "bug": ["bg", "bug"],
    "fix": ["fik", "fix"],
    "error": ["eror", "error", "err"],
    "problem": ["prblm", "problem", "prob"],
    "solution": ["solushn", "solution", "sol"],
    "test": ["tst", "test"],
    "run": ["rn", "run"],
    "build": ["bild", "build"],
    "deploy": ["deplo", "deploy"],
    "push": ["psh", "push"],
    "pull": ["pl", "pull"],
    "commit": ["comit", "commit"],
    "branch": ["branch", "brnch"],
    "merge": ["merj", "merge"],
    "review": ["revu", "review"],
    "approve": ["aprov", "approve"],
    "reject": ["rejkt", "reject"],
}


class Normalizer:
    """Text normalizer for Hinglish evaluation."""

    def __init__(self, variants_path: Optional[Path] = None):
        self.variants = self._load_variants(variants_path)
        self._canonical_map = self._build_canonical_map()
        # Common punctuation to strip (keep some for potential sentence boundaries)
        self.punctuation_pattern = re.compile(r'[।\.।,\?\!\;\:\'\"\(\)\[\]\{\}\-\—\…\…\…\*\_\+\=\~\`\@\#\$\%\^\&\*\\\|\\\/\<\>]')
        # Multiple whitespace
        self.whitespace_pattern = re.compile(r'\s+')
        # Number words
        self.number_words = {
            '0': 'zero', '1': 'ek', '2': 'do', '3': 'teen', '4': 'chaar',
            '5': 'paanch', '6': 'che', '7': 'saat', '8': 'aath', '9': 'nau',
            '10': 'das', '11': 'gyarah', '12': 'barah', '13': 'terah',
            '14': 'chaudah', '15': 'pandrah', '16': 'solah', '17': 'satrah',
            '18': 'atharah', '19': 'unnis', '20': 'bees'
        }

    def _load_variants(self, variants_path: Optional[Path]) -> Dict[str, List[str]]:
        """Load variants from YAML file, falling back to defaults."""
        if variants_path and variants_path.exists():
            with open(variants_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if data and 'variants' in data:
                    return data['variants']
        return DEFAULT_VARIANTS

    def _build_canonical_map(self) -> Dict[str, str]:
        """Build reverse mapping from variant to canonical form."""
        canonical = {}
        for canonical_form, variants in self.variants.items():
            canonical[canonical_form] = canonical_form  # Identity
            for variant in variants:
                canonical[variant.lower()] = canonical_form
        return canonical

    def _transliterate_devanagari(self, text: str) -> str:
        """Transliterate Devanagari to Roman script (ITRANS scheme)."""
        if not INDIC_AVAILABLE:
            return text
        try:
            # Detect if text contains Devanagari
            has_devanagari = any('\u0900' <= c <= '\u097F' for c in text)
            if not has_devanagari:
                return text
            return transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS).lower()
        except Exception:
            return text

    def _normalize_numbers(self, text: str) -> str:
        """Normalize numbers to words (basic)."""
        # Replace standalone digits with words
        def replace_digit(match):
            digit = match.group(0)
            return self.number_words.get(digit, digit)
        # Simple replacement for common cases
        for digit, word in self.number_words.items():
            text = re.sub(rf'\b{digit}\b', word, text)
        return text

    def _apply_variants(self, text: str) -> str:
        """Apply variant canonicalization."""
        words = text.split()
        normalized = []
        for word in words:
            lower_word = word.lower()
            normalized.append(self._canonical_map.get(lower_word, word))
        return ' '.join(normalized)

    def normalize(self, text: str) -> str:
        """
        Full normalization pipeline.
        Input: raw text (reference or hypothesis)
        Output: normalized text for comparison
        """
        if not text:
            return ""

        # 1. NFC Unicode normalization
        text = unicodedata.normalize('NFC', text)

        # 2. Transliterate Devanagari to Roman
        text = self._transliterate_devanagari(text)

        # 3. Lowercase
        text = text.lower()

        # 4. Normalize numbers
        text = self._normalize_numbers(text)

        # 5. Strip punctuation (but preserve apostrophes in contractions?)
        text = self.punctuation_pattern.sub(' ', text)

        # 6. Collapse whitespace
        text = self.whitespace_pattern.sub(' ', text).strip()

        # 7. Apply variant canonicalization
        text = self._apply_variants(text)

        # 8. Final whitespace collapse
        text = self.whitespace_pattern.sub(' ', text).strip()

        return text

    def normalize_batch(self, texts: List[str]) -> List[str]:
        """Normalize a list of texts."""
        return [self.normalize(t) for t in texts]


def load_variants_yaml(variants_path: Path) -> Dict:
    """Load variants.yaml, creating with defaults if not exists."""
    if variants_path.exists():
        with open(variants_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    else:
        # Create default variants.yaml
        data = {'variants': DEFAULT_VARIANTS}
        with open(variants_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=True)
        return data


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Text normalization for Hinglish evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval/normalize.py --text "Yeh kya hai?"
  python eval/normalize.py --file eval/desk/SPONT_SOLO.ref.txt --output normalized.txt
  python eval/normalize.py --interactive
        """
    )
    parser.add_argument('--text', help="Text to normalize (single string)")
    parser.add_argument('--file', help="Input file (one line per segment)")
    parser.add_argument('--output', help="Output file (default: stdout)")
    parser.add_argument('--interactive', action='store_true', help="Interactive mode")
    parser.add_argument('--variants', default='eval/variants.yaml', help="Variants YAML path")
    args = parser.parse_args()

    normalizer = Normalizer(Path(args.variants) if args.variants else None)

    if args.interactive:
        print("Interactive normalization (Ctrl+C to exit)")
        print("Enter text to normalize:")
        while True:
            try:
                line = input("> ")
                if line:
                    print(normalizer.normalize(line))
            except (EOFError, KeyboardInterrupt):
                break
        return 0

    if args.text:
        result = normalizer.normalize(args.text)
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(result + '\n')
        else:
            print(result)
        return 0

    if args.file:
        input_path = Path(args.file)
        if not input_path.exists():
            print(f"❌ File not found: {input_path}")
            return 1
        with open(input_path, 'r', encoding='utf-8') as f:
            lines = [line.rstrip('\n') for line in f]
        results = normalizer.normalize_batch(lines)
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write('\n'.join(results) + '\n')
        else:
            for r in results:
                print(r)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())