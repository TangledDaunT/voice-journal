"""Deterministic ownership of timestamped words from overlapping ASR context."""


def owned_words(payload, start_sample, end_sample, sample_rate):
    words = payload.get("words") or []
    if not words:
        return "[Boundary transcript needs review]", "boundary_timestamps_missing"
    selected = []
    try:
        for word in words:
            midpoint = (float(word["start"]) + float(word["end"])) / 2 * sample_rate
            if start_sample <= midpoint < end_sample:
                selected.append(word["word"].strip())
    except (KeyError, TypeError, ValueError):
        return "[Boundary transcript needs review]", "boundary_timestamps_missing"
    return " ".join(selected), None
