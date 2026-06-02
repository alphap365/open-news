"""Lightweight text summarization utilities."""

import logging
import re
from typing import List, Dict

logger = logging.getLogger(__name__)


def summarize_text_simple(text: str, sentence_count: int = 3) -> str:
    """
    Simple extractive summarization based on sentence scoring.
    
    **Why this approach:**
    - ✅ No heavy NLP library overhead (vs sumy.LsaSummarizer)
    - ✅ Works offline, deterministic results
    - ✅ Fast and reliable
    - ⚠️ Uses frequency-based scoring (not semantic)
    
    **How it works:**
    1. Split text into sentences
    2. Score each sentence by word frequency
    3. Return top N sentences in original order
    """
    if not text or len(text.strip()) < 100:
        return text[:300]
    
    # Split into sentences (simple regex-based)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) <= sentence_count:
        return ' '.join(sentences)
    
    # Score sentences by word frequency
    words = re.findall(r'\b[a-z]{2,}\b', text.lower())
    
    # Simple word frequency (ignore common words)
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'that', 'this',
        'it', 'from', 'as', 'by', 'if', 'not', 'you', 'we', 'they', 'he', 'she'
    }
    
    word_freq = {}
    for word in words:
        if word not in stopwords and len(word) > 3:
            word_freq[word] = word_freq.get(word, 0) + 1
    
    if not word_freq:
        return ' '.join(sentences[:sentence_count])
    
    # Score each sentence
    max_freq = max(word_freq.values())
    sentence_scores = []
    
    for idx, sentence in enumerate(sentences):
        score = 0
        words_in_sent = re.findall(r'\b[a-z]{2,}\b', sentence.lower())
        for word in words_in_sent:
            if word in word_freq:
                score += word_freq[word] / max_freq
        sentence_scores.append((idx, score, sentence))
    
    # Get top N sentences by score, maintain original order
    top_sentences = sorted(sentence_scores, key=lambda x: x[1], reverse=True)[:sentence_count]
    top_sentences = sorted(top_sentences, key=lambda x: x[0])  # restore order
    
    summary = ' '.join([s[2] for s in top_sentences])
    return summary


def summarize_text_with_keywords(text: str, sentence_count: int = 3, top_words: int = 5) -> Dict:
    """
    Summarize text and extract top keywords.
    
    **Returns:**
    ```python
    {
        "summary": "Summarized text...",
        "keywords": ["word1", "word2", ...],
        "coverage": 0.15  # % of original text
    }
    ```
    """
    summary = summarize_text_simple(text, sentence_count)
    
    words = re.findall(r'\b[a-z]{2,}\b', text.lower())
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'that', 'this'
    }
    
    word_freq = {}
    for word in words:
        if word not in stopwords and len(word) > 4:
            word_freq[word] = word_freq.get(word, 0) + 1
    
    keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:top_words]
    keywords = [word for word, _ in keywords]
    
    coverage = len(summary) / len(text) if text else 0
    
    return {
        "summary": summary,
        "keywords": keywords,
        "coverage": round(coverage, 3)
    }
