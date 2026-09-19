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


def _detect_language(text: str) -> Optional[str]:
    """Best-effort language code for a short string. None if undetectable."""
    if not _available:
        return None
    text = (text or "").strip()
    if len(text) < 12:  # too short for langdetect to be reliable
        return None
    try:
        return detect(text)
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

    kept = []
    for art in articles:
        sample = f"{art.get('title', '')} {art.get('description', '')}".strip()
        detected = _detect_language(sample)
        # Undetectable (too short, ambiguous) -> keep rather than penalize
        # the article for a guard limitation.
        if detected is None or detected == language:
            kept.append(art)

    logger.info(f"Language guard ({language}): {len(articles)} -> {len(kept)}")
    return kept