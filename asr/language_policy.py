"""Validate actual output; Whisper exposes one language hint, not a two-language allowlist."""

import unicodedata

LANGUAGES = {"hi", "hindi", "en", "english", ""}
# Do not supply fabricated example sentences: Whisper can transcribe the prompt itself.
PROMPT = None


def prompt_echo(text):
    compact = ''.join(char.lower() for char in text if char.isalnum())
    return ('hindiandenglish' in compact and ('shivangi' in compact or 'sivangi' in compact or 'shreyansh' in compact)) or ('आजकीबातचीत' in compact and ('shivangi' in compact or 'sivangi' in compact))


def violation(payload):
    language = (payload.get("language") or "").lower()
    if language not in LANGUAGES:
        return "unexpected_language"
    texts = [payload.get("text", "")]
    texts.extend(s.get("text", "") for s in payload.get("segments", []) or [])
    texts.extend(w.get("word", "") for w in payload.get("words", []) or [])
    for char in " ".join(texts):
        category = unicodedata.category(char)
        if category[0] not in ("L", "M"):
            continue  # Keep punctuation, digits, symbols and whitespace intact.
        name = unicodedata.name(char, "")
        if not ("LATIN" in name or "\u0900" <= char <= "\u097f" or char in "\u200c\u200d"):
            return "unexpected_script"
    return None
