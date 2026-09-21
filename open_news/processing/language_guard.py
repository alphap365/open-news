import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from langdetect import detect, DetectorFactory, LangDetectException
    DetectorFactory.seed = 0  # deterministic results
    _available = True
except ImportError:
    # FIX: define `detect` so tests can patch it even without langdetect.
    detect = None
    _available = False
    LangDetectException = Exception


# Codes langdetect can emit (its zh variants are normalised to "zh" below).
_SUPPORTED = {
    "af", "ar", "bg", "bn", "ca", "cs", "cy", "da", "de", "el", "en", "es", "et",
    "fa", "fi", "fr", "gu", "he", "hi", "hr", "hu", "id", "it", "ja", "kn", "ko",
    "lt", "lv", "mk", "ml", "mr", "ne", "nl", "no", "pa", "pl", "pt", "ro", "ru",
    "sk", "sl", "so", "sq", "sv", "sw", "ta", "te", "th", "tl", "tr", "uk", "ur",
    "vi", "zh",
}

# Languages langdetect confuses with close relatives, or lacks entirely.
_ALIASES = {
    "as": {"as", "bn"}, "bn": {"bn", "as"},
    "hi": {"hi", "mr", "ne"}, "mr": {"mr", "hi", "ne"}, "ne": {"ne", "hi", "mr"},
    "no": {"no", "nb", "nn", "da"}, "nb": {"no", "nb", "nn"}, "nn": {"no", "nb", "nn"},
    "ms": {"ms", "id"}, "id": {"id", "ms"},
}

_warned_unsupported: set = set()


def _primary(code: str) -> str:
    """'zh-cn' -> 'zh', 'en_US' -> 'en'."""
    return code.lower().replace("_", "-").split("-")[0]


def _accepted_codes(requested: str) -> set:
    req = _primary(requested)
    return set(_ALIASES.get(req, {req}))


def _detect_language(text: str) -> Optional[str]:
    """Best-effort primary language code for a short string. None if undetectable."""
    if not _available:
        return None
    text = (text or "").strip()
    if len(text) < 12:  # too short for langdetect to be reliable
        return None
    if detect is None:
        return None
    try:
        return _primary(detect(text))
    except LangDetectException:
        return None


def filter_by_language(articles: List[Dict], language: Optional[str]) -> List[Dict]:
    """
    Drop articles whose title+description doesn't match the requested
    language. If `language` is None, no filtering happens (pass-through).
    If langdetect isn't installed, logs a warning once and passes everything
    through rather than silently dropping results.
    """
    if not language:
        return articles

    if not _available:
        logger.warning(
            "language filtering requested but 'langdetect' isn't installed; "
            "skipping language filter. Install with: pip install langdetect"
        )
        return articles
    
    accepted = _accepted_codes(language)
    if not accepted & _SUPPORTED:
        # No detector for this language: pass through rather than drop everything.
        if language not in _warned_unsupported:
            _warned_unsupported.add(language)
            logger.warning("language=%r is not supported by langdetect; "
                           "language filter skipped", language)
        return articles
    kept = []
    for art in articles:
        sample = f"{art.get('title', '')} {art.get('description', '')}".strip()
        detected = _detect_language(sample)
        # Undetectable (too short, ambiguous) -> keep rather than penalize
        # the article for a guard limitation.
        if detected is None or detected in accepted:
            kept.append(art)

    logger.info(f"Language guard ({language}): {len(articles)} -> {len(kept)}")
    return kept