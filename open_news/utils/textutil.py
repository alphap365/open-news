"""Unicode-aware text helpers shared by the filters, dedupe and ranker."""
import re
import unicodedata


def _mark_ranges() -> str:
    ranges, start, prev = [], None, None
    for cp in range(0x0300, 0x10000):
        if unicodedata.category(chr(cp)).startswith("M"):
            if start is None:
                start = cp
            prev = cp
        elif start is not None:
            ranges.append((start, prev))
            start = None
    if start is not None:
        ranges.append((start, prev))
    return "".join(
        f"\\u{a:04x}" if a == b else f"\\u{a:04x}-\\u{b:04x}" for a, b in ranges
    )


MARKS = _mark_ranges()
WORD = rf"[\w{MARKS}]"
_NON_WORD_RE = re.compile(rf"[^\w\s{MARKS}]")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def normalize_title(title: str) -> str:
    t = _NON_WORD_RE.sub("", nfc(title).lower().strip())
    return re.sub(r"\s+", " ", t)