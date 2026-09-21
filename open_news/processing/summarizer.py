import logging
import re
from typing import List, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional NLP summarization backend: Sumy (pure Python, no HF, no LLM)
# ---------------------------------------------------------------------------
try:
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.lsa import LsaSummarizer

    _SUMY_AVAILABLE = True
except Exception:  # pragma: no cover
    _SUMY_AVAILABLE = False


def _nlp_summarize(text: str, sentence_count: int) -> str | None:
    """Try Sumy/LSA summarization. Return None if unavailable or failed."""
    if not _SUMY_AVAILABLE:
        return None
    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        sentences = summarizer(parser.document, sentence_count)
        if not sentences:
            return None
        return " ".join(str(s) for s in sentences)
    except Exception as exc:
        logger.debug("NLP summarization failed, falling back: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Original extractive fallback (unchanged logic)
# ---------------------------------------------------------------------------
def _summarize_text_fallback(text: str, sentence_count: int = 3) -> str:
    if not text or len(text.strip()) < 100:
        return text[:300]

    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= sentence_count:
        return ' '.join(sentences)

    words = re.findall(r'\b[a-z]{2,}\b', text.lower())
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'that', 'this',
        'it', 'from', 'as', 'by', 'if', 'not', 'you', 'we', 'they', 'he', 'she'
    }

    word_freq: Dict[str, int] = {}
    for word in words:
        if word not in stopwords and len(word) > 3:
            word_freq[word] = word_freq.get(word, 0) + 1

    if not word_freq:
        return ' '.join(sentences[:sentence_count])

    max_freq = max(word_freq.values())
    sentence_scores: List[tuple[int, float, str]] = []

    for idx, sentence in enumerate(sentences):
        score = 0.0
        words_in_sent = re.findall(r'\b[a-z]{2,}\b', sentence.lower())
        for word in words_in_sent:
            if word in word_freq:
                score += word_freq[word] / max_freq
        sentence_scores.append((idx, score, sentence))

    top_sentences = sorted(sentence_scores, key=lambda x: x[1], reverse=True)[:sentence_count]
    top_sentences = sorted(top_sentences, key=lambda x: x[0])
    summary = ' '.join([s[2] for s in top_sentences])
    return summary


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def summarize_text(text: str, sentence_count: int = 3) -> str:
    """
    Simple extractive summarization based on sentence scoring.

    Tries an NLP backend (Sumy LSA) first. Falls back to the original
    frequency-based extractive method if Sumy is unavailable or fails.

    Args:
        text: Input text.
        sentence_count: Number of sentences to include.

    Returns:
        Summarized text.
    """
    if not text or len(text.strip()) < 100:
        return text[:300]

    nlp_summary = _nlp_summarize(text, sentence_count)
    if nlp_summary:
        return nlp_summary

    return _summarize_text_fallback(text, sentence_count)


def summarize_with_keywords(text: str, sentence_count: int = 3, top_words: int = 5) -> Dict:
    """
    Summarize text and extract top keywords.

    Returns:
        dict with keys: summary, keywords, coverage.
    """
    summary = summarize_text(text, sentence_count)

    words = re.findall(r'\b[a-z]{2,}\b', text.lower())
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'that', 'this'
    }

    word_freq: Dict[str, int] = {}
    for word in words:
        if word not in stopwords and len(word) > 4:
            word_freq[word] = word_freq.get(word, 0) + 1

    ranked_keywords: List[tuple[str, int]] = sorted(
        word_freq.items(), key=lambda x: x[1], reverse=True
    )[:top_words]
    keywords: List[str] = [word for word, _ in ranked_keywords]

    coverage = len(summary) / len(text) if text else 0.0

    return {
        "summary": summary,
        "keywords": keywords,
        "coverage": round(coverage, 3)
    }