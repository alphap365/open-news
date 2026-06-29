#!/usr/bin/env python3
"""
FastArticleExtractor – A single‑file, zero‑dependency article extractor that
merges the stopword‑based scoring of newspaper3k with the fallback cascade and
configurable thresholds of trafilatura.
"""

import re
import sys
from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

from dateutil import parser as date_parser
from lxml import etree
from lxml.html import HtmlElement, fromstring, tostring


# ----------------------------------------------------------------------
# Configurable thresholds (trafilatura style)
# ----------------------------------------------------------------------

SCORE_WEIGHTS = {
    "stopword_bonus": 3,           # points per stopword
    "negative_link_density": -5,   # penalty per link‑density unit (if > threshold)
    "sibling_accept_ratio": 0.3,   # threshold for pulling in siblings
}

STRICT_DATE_REGEX = re.compile(r'/(\d{4})/(\d{2})/(\d{2})/')

DEFAULT_CONFIG = {
    "min_text_length": 200,               # Minimum characters for considered extraction
    "max_link_density": 0.5,              # If link/text > this, node penalised
    "stopword_bonus": 3,                  # Points per stopword found
    "tag_bonus": {
        "article": 10,
        "main": 10,
        "section": 5,
        "div_content": 3,
    },
    "sibling_accept_ratio": 0.3,          # Score threshold to pull in siblings
    "fallback_min_paragraphs": 2,         # Minimum paragraphs for fallback extraction
}

LANGUAGE_STOPWORDS = {
    "en": {"the", "and", "for", "that", "this", "with", "from", "have",
           "are", "was", "were", "be", "been", "being", "in", "on", "at"},
}

AUTHOR_META = ["author", "article:author", "byline", "dc.creator", "sailthru.author"]
DATE_META = [
    "article:published_time", "datePublished", "pubdate", "publish_date",
    "og:published_time", "datetime", "date"
]
VIDEO_PROVIDERS = ["youtube", "youtu.be", "vimeo", "dailymotion", "twitch"]


class FastArticleExtractor:
    def __init__(self, language: str = "en", config: dict = None):
        self.language = language[:2].lower()
        self.stopwords = LANGUAGE_STOPWORDS.get(self.language, LANGUAGE_STOPWORDS["en"])
        self.config = {**DEFAULT_CONFIG, **(config or {})}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract(self, html: str, url: Optional[str] = None) -> Dict:
        """Return full article data as a dict."""
        doc = fromstring(html)
        if url:
            doc.make_links_absolute(url)

        meta = self._extract_metadata(doc, url)
        title = self._extract_title(doc, meta)
        authors = self._extract_authors(doc, meta)
        pub_date = self._extract_pubdate(doc, url, meta)
        category = self._extract_category(doc, url, meta)

        # Main text extraction (newspaper style with trafilatura fallback)
        text, top_node = self._extract_text(doc)

        images = self._extract_images(doc, top_node, url)
        videos = self._extract_videos(doc, top_node)

        return {
            "title": title,
            "authors": authors,
            "publish_date": pub_date.isoformat() if pub_date else None,
            "category": category,
            "text": text,
            "top_image": images[0] if images else None,
            "images": images,
            "videos": videos,
            "meta": meta,
        }

    # ------------------------------------------------------------------
    # Text extraction core (newspaper's scoring + climbing + siblings)
    # ------------------------------------------------------------------
    def _extract_text(self, doc: HtmlElement) -> Tuple[str, Optional[HtmlElement]]:
        """Try newspaper‑style extraction first, fall back to generic density."""
        top_node = self._get_best_node(doc)
        if top_node is not None:
            # Expand with siblings that score above threshold
            base_score = self.score_node(top_node)
            siblings = self._get_siblings(top_node, base_score)
            for sib in siblings:
                top_node.addprevious(sib)

            cleaned = self._clean_node(top_node)
            text = " ".join(p.text_content().strip()
                            for p in cleaned.xpath(".//p") if p.text_content())

            if len(text) >= self.config["min_text_length"]:
                return text, top_node

        # Fallback: trafilatura's generic text‑density method
        return self._fallback_text_extraction(doc), None

    def score_node(self, node: HtmlElement) -> float:
        """Score a node based on stopword count, tag importance, link density."""
        text = node.text_content()
        if not text:
            return 0.0
        # Count stopwords (simple tokenization)
        words = re.findall(r"[A-Za-z\u00C0-\u00FF]+", text.lower())
        stopword_count = sum(1 for w in words if w in self.stopwords)

        # Tag bonus
        tag_bonus = 0
        tag = node.tag.lower()
        if tag in ("article", "main"):
            tag_bonus = 10
        elif tag == "section":
            tag_bonus = 5
        elif tag == "div" and node.get("class", "").find("content") != -1:
            tag_bonus = 3

        score = stopword_count * SCORE_WEIGHTS["stopword_bonus"] + tag_bonus

        # Penalize high link density on top of the computed score, rather than
        # discarding tag_bonus alone — this keeps nav-heavy blocks from
        # still scoring positively when they're also stopword-dense.
        if self._link_density(node) > self.config["max_link_density"]:
            score += SCORE_WEIGHTS["negative_link_density"] * 4  # -20 total, applied to full score

        return score

    def _link_density(self, node: HtmlElement) -> float:
        total = len((node.text_content() or "").strip())
        if total == 0:
            return 1.0
        links = node.xpath(".//a")
        link_len = sum(len(a.text_content().strip()) for a in links)
        return link_len / total

    def _get_best_node(self, doc: HtmlElement) -> Optional[HtmlElement]:
        """Find the node with highest density of stopword-rich text."""
        candidates = doc.xpath(".//p|.//article|.//div[contains(@class, 'content')]|.//section")
        scored = []
        for node in candidates:
            s = self.score_node(node)
            if s > 0:
                scored.append((s, node))
        if not scored:
            return None
        scored.sort(reverse=True, key=lambda x: x[0])
        best = scored[0][1]
        best_score = scored[0][0]

        # Walk up to a more meaningful parent if score improves, but cap depth
        # and never walk past <body> to avoid grabbing the whole page.
        parent = best.getparent()
        max_hops = 4
        hops = 0
        while parent is not None and parent != doc and hops < max_hops:
            if parent.tag.lower() in ("body", "html"):
                break
            parent_score = self.score_node(parent)
            if parent_score > best_score * 1.2:
                best = parent
                best_score = parent_score
            parent = parent.getparent()
            hops += 1
        return best

    def _get_siblings(self, top: HtmlElement, base_score: float) -> List[HtmlElement]:
        """Add preceding siblings that have plausible content."""
        candidates = []  # collect (sibling_node, list_of_p_nodes_to_keep) without mutating yet
        for sib in list(top.itersiblings(preceding=True)):  # snapshot before any mutation
            if sib.tag == "p":
                s = self.score_node(sib)
                if s > base_score * SCORE_WEIGHTS["sibling_accept_ratio"]:
                    candidates.append(sib)
            elif sib.tag in ("div", "section"):
                for p in sib.xpath(".//p"):
                    s = self.score_node(p)
                    if s > base_score * SCORE_WEIGHTS["sibling_accept_ratio"]:
                        candidates.append(p)
        return candidates

    def _clean_node(self, node: HtmlElement) -> HtmlElement:
        """Deep copy and strip non‑content tags (newspaper + trafilatura)."""
        clean = deepcopy(node)
        # Trafilatura's list of boilerplate tags
        for sel in ["script", "style", "nav", "aside", "footer", "header",
                    "form", "button", "noscript", "meta", "link"]:
            for el in clean.xpath(f".//{sel}"):
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
        return clean

    def _fallback_text_extraction(self, doc: HtmlElement) -> str:
        """
        Generic text‑density fallback (inspired by trafilatura's bare extraction).
        Returns all text nodes that are not inside obvious noise elements.
        """
        # Remove clearly irrelevant nodes
        for sel in ["nav", "footer", "header", "aside", "script", "style", "noscript"]:
            for el in doc.xpath(f".//{sel}"):
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)

        # Collect text from paragraphs and divs with sufficient length
        texts = []
        for node in doc.xpath(".//p | .//div"):
            txt = node.text_content().strip()
            if len(txt) > 120:          # heuristic length
                texts.append(txt)
        if len(texts) >= self.config["fallback_min_paragraphs"]:
            return "\n\n".join(texts)

        # Ultimate fallback: everything but keep it short
        all_text = doc.text_content()
        lines = (line.strip() for line in all_text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return "\n".join(chunk for chunk in chunks if chunk)

    # ------------------------------------------------------------------
    # Metadata extractors (heavy use of trafilatura's meta tag approach)
    # ------------------------------------------------------------------
    def _extract_metadata(self, doc: HtmlElement, url: Optional[str]) -> Dict:
        meta = {}
        # Language
        lang = doc.get("lang") or doc.get("xml:lang")
        if lang:
            meta["language"] = lang[:2]
        # Canonical
        canonical = doc.xpath('//link[@rel="canonical"]/@href')
        meta["canonical"] = canonical[0] if canonical else (url or "")
        # Description
        desc = doc.xpath('//meta[@name="description"]/@content|//meta[@property="og:description"]/@content')
        meta["description"] = desc[0] if desc else ""
        # Site name
        site = doc.xpath('//meta[@property="og:site_name"]/@content')
        meta["site_name"] = site[0] if site else ""
        # Keywords
        kw = doc.xpath('//meta[@name="keywords"]/@content')
        meta["keywords"] = [k.strip() for k in kw[0].split(",")] if kw else []
        # JSON‑LD
        meta["json_ld"] = self._extract_json_ld(doc)
        return meta

    def _extract_title(self, doc: HtmlElement, meta: Dict) -> str:
        # Order: og:title > title tag > h1 > meta title
        og = doc.xpath('//meta[@property="og:title"]/@content')
        if og and og[0]:
            return og[0].strip()
        title_tag = doc.xpath('//title/text()')
        if title_tag:
            t = title_tag[0].strip()
            for delim in ["|", "-", "»", "–"]:
                if delim in t:
                    t = max((p.strip() for p in t.split(delim)), key=len)
                    break
            return t
        h1 = doc.xpath('//h1/text()')
        if h1:
            return h1[0].strip()
        return ""

    def _extract_authors(self, doc: HtmlElement, meta: Dict) -> List[str]:
        authors = set()
        for name in AUTHOR_META:
            vals = doc.xpath(f'//meta[@name="{name}"]/@content|//meta[@property="{name}"]/@content')
            for v in vals:
                authors.add(v.strip())
        # Byline classes
        byline = doc.xpath('//*[contains(@class, "byline") or contains(@class, "author")]//text()')
        if byline:
            txt = " ".join(byline).strip()
            parts = re.split(r'[·|,]|\sand\s|\set\s', txt, flags=re.I)
            for p in parts:
                p = p.strip()
                if p and not re.search(r'\d', p) and len(p) > 2:
                    authors.add(p)
        # JSON‑LD
        j = meta.get("json_ld", {})
        if "author" in j:
            auth = j["author"]
            if isinstance(auth, str):
                authors.add(auth)
            elif isinstance(auth, dict) and "name" in auth:
                authors.add(auth["name"])
        return list(authors)

    def _extract_pubdate(self, doc: HtmlElement, url: Optional[str], meta: Dict) -> Optional[datetime]:
        for name in DATE_META:
            vals = doc.xpath(f'//meta[@name="{name}"]/@content|//meta[@property="{name}"]/@content')
            if vals:
                try:
                    return date_parser.parse(vals[0])
                except Exception:
                    pass

        j = meta.get("json_ld", {})
        for key in ["datePublished", "dateCreated", "dateModified"]:
            if key in j:
                try:
                    return date_parser.parse(j[key])   # was: date_parser(j[key])
                except Exception:
                    pass

        time_tags = doc.xpath('//time/@datetime')
        if time_tags:
            try:
                return date_parser.parse(time_tags[0])   # was: date_parser(time_tags[0])
            except Exception:
                pass

        # Last resort: guess from URL path, e.g. /2024/03/15/headline
        if url:
            m = STRICT_DATE_REGEX.search(url)
            if m:
                try:
                    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except Exception:
                    pass

        return None

    def _extract_images(self, doc: HtmlElement, top_node: Optional[HtmlElement], url: Optional[str]) -> List[str]:
        imgs = []
        # Open Graph image
        og_img = doc.xpath('//meta[@property="og:image"]/@content')
        if og_img and url:
            imgs.append(urljoin(url, og_img[0]))
        # Inside the article body
        if top_node is not None:
            for img in top_node.xpath(".//img"):
                src = img.get("src") or img.get("data-src")
                if src:
                    if src.startswith("http"):
                        imgs.append(src)
                    elif url:
                        imgs.append(urljoin(url, src))
        return list(dict.fromkeys(imgs))   # deduplicate

    def _extract_videos(self, doc: HtmlElement, top_node: Optional[HtmlElement]) -> List[str]:
        videos = []
        if top_node is None:
            return videos
        for iframe in top_node.xpath(".//iframe"):
            src = iframe.get("src", "")
            if any(provider in src for provider in VIDEO_PROVIDERS):
                videos.append(src)
        # og:video
        og_video = doc.xpath('//meta[@property="og:video"]/@content')
        if og_video:
            videos.append(og_video[0])
        # JSON‑LD
        j = self._extract_json_ld(doc)
        if "video" in j and "contentUrl" in j["video"]:
            videos.append(j["video"]["contentUrl"])
        return list(dict.fromkeys(videos))

    def _extract_json_ld(self, doc: HtmlElement) -> Dict:
        """Parse JSON-LD scripts into a dict (simplified)."""
        import json
        data = {}
        for script in doc.xpath('//script[@type="application/ld+json"]'):
            try:
                j = json.loads(script.text)
            except Exception:
                continue

            items = j if isinstance(j, list) else [j]
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Prefer Article-like schemas; skip Organization/WebSite blocks
                # unless we have nothing yet, so they don't clobber real data.
                schema_type = item.get("@type", "")
                is_article_like = "Article" in schema_type or "NewsArticle" in schema_type
                for key, value in item.items():
                    if key not in data or (is_article_like and key in ("datePublished", "dateCreated", "dateModified", "author", "headline")):
                        data[key] = value
        return data

    def _extract_category(self, doc: HtmlElement, url: Optional[str], meta: Dict) -> str:
        """Best-effort section/category: meta tag first, then URL path segment."""
        section = doc.xpath('//meta[@property="article:section"]/@content')
        if section and section[0].strip():
            return section[0].strip()

        og_section = doc.xpath('//meta[@property="og:section"]/@content')
        if og_section and og_section[0].strip():
            return og_section[0].strip()

        if url:
            path = urlparse(url).path.strip("/")
            segments = [s for s in path.split("/") if s]
            # skip purely numeric or date-like segments (years, ids)
            for seg in segments:
                if not seg.isdigit() and len(seg) > 2:
                    return seg.replace("-", " ").title()

        return ""

def extract_article(html: str, url: Optional[str] = None) -> Dict:
    """Convenience function for FastArticleExtractor.extract_article."""
    extractor = FastArticleExtractor()
    return extractor.extract(html, url)