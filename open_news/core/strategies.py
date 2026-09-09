import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from dateutil import parser as date_parser
from lxml.html import HtmlElement

logger = logging.getLogger(__name__)

ALL_FIELDS: Set[str] = {
    "title", "authors", "publish_date", "category", "text",
    "top_image", "images", "videos",
    "description", "site_name", "keywords", "language", "canonical",
}

VIDEO_PROVIDERS = ["youtube", "youtu.be", "vimeo", "dailymotion", "twitch"]
AUTHOR_META = ["author", "article:author", "byline", "dc.creator", "sailthru.author"]
DATE_META = [
    "article:published_time", "datePublished", "pubdate", "publish_date",
    "og:published_time", "datetime", "date",
]
STRICT_DATE_REGEX = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")

# Earliest plausible publish year and how far into the future a date can
# drift (clock skew / scheduled-embargo pages) before we distrust it.
MIN_VALID_YEAR = 1995
MAX_FUTURE_SKEW = timedelta(days=2)

# Filename/URL fragments that reliably indicate chrome, not content:
# icons, logos, avatars, sprites, tracking pixels, social-share badges.
JUNK_IMAGE_PATTERNS = re.compile(
    r"(?:^data:|/favicon|sprite|1x1|pixel\.(?:gif|png)|"
    r"logo[-_.]|icon[-_.]|avatar|placeholder|blank\.(?:gif|png)|"
    r"spacer\.(?:gif|png)|badge|social[-_]share)",
    re.I,
)

# Common byline noise words / role suffixes to strip before treating a
# token as a person's name.
AUTHOR_PREFIX_RE = re.compile(r"^\s*by\s+", re.I)
AUTHOR_ROLE_SUFFIX_RE = re.compile(
    r"\s*[\(\|,-]\s*(staff writer|correspondent|reporter|editor|contributor|"
    r"opinion|columnist|special to.*|updated.*|published.*)\s*$", re.I,
)


def _empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _valid_date(dt: Optional[datetime]) -> Optional[datetime]:
    """Reject obviously-wrong parses: pre-1995 (almost always a mis-parsed
    fragment, not a real online publish date) or further in the future than
    a couple of days can account for."""
    if dt is None:
        return None
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    if dt.year < MIN_VALID_YEAR:
        return None
    if dt > now + MAX_FUTURE_SKEW:
        return None
    return dt


def _clean_author_name(raw: str) -> Optional[str]:
    """Strip 'By ' prefixes, trailing role/date annotations, digits-only
    junk, and enforce a plausible name length."""
    name = AUTHOR_PREFIX_RE.sub("", raw).strip()
    name = AUTHOR_ROLE_SUFFIX_RE.sub("", name).strip(" -|,")
    if not name or len(name) < 3 or len(name) > 60:
        return None
    if re.search(r"\d", name):
        return None
    # Reject things that are clearly not names: all-caps section labels,
    # or strings without at least one space (single-word "names" are
    # usually nav labels like "Sports" leaking through a bad selector).
    if name.isupper() and len(name) > 12:
        return None
    return name


def _is_junk_image(url: str) -> bool:
    return bool(JUNK_IMAGE_PATTERNS.search(url))


def _absolutize(url: Optional[str], base: Optional[str]) -> Optional[str]:
    if not url:
        return url
    if url.startswith("http"):
        return url
    return urljoin(base, url) if base else url


class ExtractionStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def extract(self, doc: HtmlElement, url: Optional[str], needed: Set[str]) -> Dict[str, Any]:
        """Return a dict containing only fields (subset of `needed`) this
        strategy could actually determine. Omit fields it can't answer —
        do not return None/"" placeholders, the coordinator treats those
        as 'not found' anyway but skipping them avoids wasted work."""
        raise NotImplementedError


# ----------------------------------------------------------------------
# 1. JSON-LD (schema.org Article / NewsArticle)
# ----------------------------------------------------------------------
class JsonLdStrategy(ExtractionStrategy):
    """Best source for: title, authors, publish_date, category, images,
    videos, site_name, description, language — when the publisher bothers
    to emit schema.org markup (most modern CMSs do)."""

    name = "json_ld"

    def extract(self, doc: HtmlElement, url: Optional[str], needed: Set[str]) -> Dict[str, Any]:
        ld = self._parse(doc)
        if not ld:
            return {}

        out: Dict[str, Any] = {}

        if "title" in needed:
            val = ld.get("headline") or ld.get("name")
            if isinstance(val, str) and val.strip():
                out["title"] = val.strip()

        if "authors" in needed:
            authors = self._authors(ld)
            if authors:
                out["authors"] = authors

        if "publish_date" in needed:
            for key in ("datePublished", "dateCreated", "dateModified"):
                if ld.get(key):
                    try:
                        parsed = _valid_date(date_parser.parse(ld[key]))
                    except Exception:
                        parsed = None
                    if parsed:
                        out["publish_date"] = parsed
                        break

        if "category" in needed:
            sect = ld.get("articleSection")
            if sect:
                out["category"] = sect if isinstance(sect, str) else str(sect[0])

        if "description" in needed and isinstance(ld.get("description"), str) and ld["description"].strip():
            out["description"] = ld["description"].strip()

        if "site_name" in needed:
            pub = ld.get("publisher")
            if isinstance(pub, dict) and pub.get("name"):
                out["site_name"] = pub["name"]

        if ("top_image" in needed or "images" in needed):
            imgs = self._images(ld, url)
            if imgs:
                out["images"] = imgs
                if "top_image" in needed:
                    out["top_image"] = imgs[0]

        if "videos" in needed:
            vids = self._videos(ld)
            if vids:
                out["videos"] = vids

        if "language" in needed and isinstance(ld.get("inLanguage"), str):
            out["language"] = ld["inLanguage"][:2]

        return out

    # -- helpers ---------------------------------------------------
    def _parse(self, doc: HtmlElement) -> Dict:
        """Merge all JSON-LD blocks, preferring Article/NewsArticle types
        for fields that conflict with Organization/WebSite/Breadcrumb blocks."""
        data: Dict[str, Any] = {}
        for script in doc.xpath('//script[@type="application/ld+json"]'):
            try:
                parsed = json.loads(script.text)
            except Exception:
                continue
            items = parsed if isinstance(parsed, list) else [parsed]
            # unwrap @graph containers
            expanded = []
            for item in items:
                if isinstance(item, dict) and "@graph" in item and isinstance(item["@graph"], list):
                    expanded.extend(item["@graph"])
                else:
                    expanded.append(item)
            for item in expanded:
                if not isinstance(item, dict):
                    continue
                schema_type = str(item.get("@type", ""))
                is_article = "Article" in schema_type or "NewsArticle" in schema_type or "BlogPosting" in schema_type
                for key, value in item.items():
                    if key not in data or is_article:
                        data[key] = value
        return data

    def _authors(self, ld: Dict) -> List[str]:
        auth = ld.get("author")
        names: List[str] = []
        if isinstance(auth, str):
            names.append(auth)
        elif isinstance(auth, dict):
            if auth.get("name"):
                names.append(auth["name"])
        elif isinstance(auth, list):
            for a in auth:
                if isinstance(a, dict) and a.get("name"):
                    names.append(a["name"])
                elif isinstance(a, str):
                    names.append(a)
        cleaned = [_clean_author_name(n) for n in names if n]
        return list(dict.fromkeys(n for n in cleaned if n))

    def _images(self, ld: Dict, url: Optional[str]) -> List[str]:
        img = ld.get("image")
        urls: List[str] = []
        if isinstance(img, str):
            urls.append(img)
        elif isinstance(img, dict) and img.get("url"):
            urls.append(img["url"])
        elif isinstance(img, list):
            for i in img:
                if isinstance(i, str):
                    urls.append(i)
                elif isinstance(i, dict) and i.get("url"):
                    urls.append(i["url"])
        return list(dict.fromkeys(_absolutize(u, url) for u in urls if u))

    def _videos(self, ld: Dict) -> List[str]:
        vid = ld.get("video")
        urls: List[str] = []
        candidates = vid if isinstance(vid, list) else [vid] if vid else []
        for v in candidates:
            if isinstance(v, dict):
                url = v.get("contentUrl") or v.get("embedUrl")
                if url:
                    urls.append(url)
        return list(dict.fromkeys(urls))


# ----------------------------------------------------------------------
# 2. OpenGraph / Twitter Card / article: meta tags
# ----------------------------------------------------------------------
class OpenGraphStrategy(ExtractionStrategy):
    """Best source for: description, site_name, top_image, canonical, and
    a solid fallback for title/author/date/category when JSON-LD is absent
    or incomplete. Every modern site ships OG tags even without JSON-LD."""

    name = "open_graph"

    def extract(self, doc: HtmlElement, url: Optional[str], needed: Set[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}

        if "title" in needed:
            v = self._meta(doc, "og:title") or self._meta(doc, "twitter:title", attr="name")
            if v:
                out["title"] = v.strip()

        if "description" in needed:
            v = (self._meta(doc, "og:description")
                 or self._meta(doc, "description", attr="name")
                 or self._meta(doc, "twitter:description", attr="name"))
            if v:
                out["description"] = v.strip()

        if "site_name" in needed:
            v = self._meta(doc, "og:site_name")
            if v:
                out["site_name"] = v.strip()

        if "canonical" in needed:
            c = doc.xpath('//link[@rel="canonical"]/@href')
            if c and c[0].strip():
                out["canonical"] = c[0].strip()

        if "authors" in needed:
            names = []
            for name in AUTHOR_META:
                for v in doc.xpath(f'//meta[@name="{name}"]/@content|//meta[@property="{name}"]/@content'):
                    cleaned = _clean_author_name(v) if v.strip() else None
                    if cleaned:
                        names.append(cleaned)
            if names:
                out["authors"] = list(dict.fromkeys(names))

        if "publish_date" in needed:
            for name in DATE_META:
                for v in doc.xpath(f'//meta[@name="{name}"]/@content|//meta[@property="{name}"]/@content'):
                    try:
                        parsed = _valid_date(date_parser.parse(v))
                    except Exception:
                        parsed = None
                    if parsed:
                        out["publish_date"] = parsed
                        break
                if "publish_date" in out:
                    break

        if "category" in needed:
            # Prefer breadcrumb nav (most sites mark it up, and it reflects
            # the site's own taxonomy) over the single og:section meta tag.
            crumb = self._breadcrumb_category(doc)
            v = crumb or self._meta(doc, "article:section") or self._meta(doc, "og:section")
            if v:
                out["category"] = v.strip()

        if "keywords" in needed:
            kw = doc.xpath('//meta[@name="keywords"]/@content')
            if kw and kw[0].strip():
                out["keywords"] = [k.strip() for k in kw[0].split(",") if k.strip()]

        if "language" in needed:
            lang = doc.get("lang") or doc.get("xml:lang") or self._meta(doc, "og:locale")
            if lang:
                out["language"] = lang[:2]

        if "top_image" in needed or "images" in needed:
            v = self._meta(doc, "og:image") or self._meta(doc, "twitter:image", attr="name")
            if v and not _is_junk_image(v):
                abs_url = _absolutize(v, url)
                out["images"] = [abs_url]
                if "top_image" in needed:
                    out["top_image"] = abs_url

        if "videos" in needed:
            v = self._meta(doc, "og:video") or self._meta(doc, "og:video:url")
            if v:
                out["videos"] = [v]

        return out

    def _meta(self, doc: HtmlElement, key: str, attr: str = "property") -> Optional[str]:
        vals = doc.xpath(f'//meta[@{attr}="{key}"]/@content')
        return vals[0] if vals else None

    def _breadcrumb_category(self, doc: HtmlElement) -> Optional[str]:
        """Read schema.org BreadcrumbList markup or common breadcrumb nav
        classes; take the first level after Home (index 0/1)."""
        items = doc.xpath(
            '//*[contains(@class,"breadcrumb")]//a/text()'
            '|//nav[@aria-label="breadcrumb" or @aria-label="Breadcrumb"]//a/text()'
        )
        items = [i.strip() for i in items if i.strip() and i.strip().lower() not in ("home", "homepage")]
        return items[0] if items else None


# ----------------------------------------------------------------------
# 3. DOM heuristic (newspaper-style scoring/climbing + trafilatura-style
#    density fallback). Only real source for `text`; universal fallback
#    for everything else when structured data is missing/incomplete.
# ----------------------------------------------------------------------
class HeuristicStrategy(ExtractionStrategy):
    name = "heuristic"

    SCORE_WEIGHTS = {
        "stopword_bonus": 3,
        "negative_link_density": -5,
        "sibling_accept_ratio": 0.3,
    }
    STOPWORDS = {
        "the", "and", "for", "that", "this", "with", "from", "have",
        "are", "was", "were", "be", "been", "being", "in", "on", "at",
    }

    def __init__(self, config: Optional[Dict] = None):
        self.config = {
            "min_text_length": 200,
            "max_link_density": 0.5,
            "fallback_min_paragraphs": 2,
            **(config or {}),
        }

    def extract(self, doc: HtmlElement, url: Optional[str], needed: Set[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        top_node = None

        if "text" in needed:
            text, top_node = self._extract_text(doc)
            if text:
                out["text"] = text

        if "title" in needed:
            v = self._title(doc)
            if v:
                out["title"] = v

        if "authors" in needed:
            v = self._authors_from_byline(doc)
            if v:
                out["authors"] = v

        if "publish_date" in needed:
            v = self._pubdate(doc, url)
            if v:
                out["publish_date"] = v

        if "category" in needed and url:
            v = self._category_from_url(url)
            if v:
                out["category"] = v

        if "description" in needed:
            # first substantial paragraph as a last-resort description
            if top_node is None:
                top_node, _ = self._get_best_node(doc), None
            if top_node is not None:
                first_p = top_node.xpath(".//p")
                if first_p:
                    txt = first_p[0].text_content().strip()
                    if len(txt) > 40:
                        out["description"] = txt[:300]

        if "site_name" in needed and url:
            domain = urlparse(url).netloc.replace("www.", "")
            if domain:
                out["site_name"] = domain.split(".")[0].title()

        if "language" in needed:
            lang = doc.get("lang") or doc.get("xml:lang")
            if lang:
                out["language"] = lang[:2]

        if "canonical" in needed and url:
            out["canonical"] = url

        if ("top_image" in needed or "images" in needed):
            imgs = self._images(doc, top_node, url)
            if imgs:
                out["images"] = imgs
                if "top_image" in needed:
                    out["top_image"] = imgs[0]

        if "videos" in needed:
            vids = self._videos(doc, top_node)
            if vids:
                out["videos"] = vids

        return out

    # ---- text extraction (newspaper-style + trafilatura fallback) ----
    def _extract_text(self, doc):
        top_node = self._get_best_node(doc)
        if top_node is not None:
            base_score = self._score(top_node)
            for sib in self._siblings(top_node, base_score):
                top_node.addprevious(sib)
            cleaned = self._clean(top_node)
            text = " ".join(p.text_content().strip() for p in cleaned.xpath(".//p") if p.text_content())
            if len(text) >= self.config["min_text_length"]:
                return text, top_node
        return self._fallback_text(doc), None

    def _score(self, node) -> float:
        text = node.text_content()
        if not text:
            return 0.0
        words = re.findall(r"[A-Za-z\u00C0-\u00FF]+", text.lower())
        stopword_count = sum(1 for w in words if w in self.STOPWORDS)
        tag = node.tag.lower()
        tag_bonus = 10 if tag in ("article", "main") else 5 if tag == "section" else (
            3 if tag == "div" and "content" in node.get("class", "") else 0)
        score = stopword_count * self.SCORE_WEIGHTS["stopword_bonus"] + tag_bonus
        if self._link_density(node) > self.config["max_link_density"]:
            score += self.SCORE_WEIGHTS["negative_link_density"] * 4
        return score

    def _link_density(self, node) -> float:
        total = len((node.text_content() or "").strip())
        if total == 0:
            return 1.0
        links = node.xpath(".//a")
        link_len = sum(len(a.text_content().strip()) for a in links)
        return link_len / total

    def _get_best_node(self, doc):
        candidates = doc.xpath(".//p|.//article|.//div[contains(@class, 'content')]|.//section")
        scored = [(self._score(n), n) for n in candidates]
        scored = [(s, n) for s, n in scored if s > 0]
        if not scored:
            return None
        scored.sort(reverse=True, key=lambda x: x[0])
        best, best_score = scored[0][1], scored[0][0]
        parent, hops = best.getparent(), 0
        while parent is not None and hops < 4:
            if parent.tag.lower() in ("body", "html"):
                break
            ps = self._score(parent)
            if ps > best_score * 1.2:
                best, best_score = parent, ps
            parent = parent.getparent()
            hops += 1
        return best

    def _siblings(self, top, base_score):
        out = []
        for sib in list(top.itersiblings(preceding=True)):
            if sib.tag == "p":
                if self._score(sib) > base_score * self.SCORE_WEIGHTS["sibling_accept_ratio"]:
                    out.append(sib)
            elif sib.tag in ("div", "section"):
                for p in sib.xpath(".//p"):
                    if self._score(p) > base_score * self.SCORE_WEIGHTS["sibling_accept_ratio"]:
                        out.append(p)
        return out

    def _clean(self, node):
        from copy import deepcopy
        clean = deepcopy(node)
        for sel in ["script", "style", "nav", "aside", "footer", "header", "form", "button", "noscript", "meta", "link"]:
            for el in clean.xpath(f".//{sel}"):
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
        return clean

    def _fallback_text(self, doc) -> str:
        for sel in ["nav", "footer", "header", "aside", "script", "style", "noscript"]:
            for el in doc.xpath(f".//{sel}"):
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
        texts = [n.text_content().strip() for n in doc.xpath(".//p | .//div")]
        texts = [t for t in texts if len(t) > 120]
        if len(texts) >= self.config["fallback_min_paragraphs"]:
            return "\n\n".join(texts)
        all_text = doc.text_content()
        lines = (line.strip() for line in all_text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return "\n".join(c for c in chunks if c)

    # ---- other fields ----
    def _title(self, doc) -> str:
        """Prefer <h1> — it's the on-page headline the reader actually sees.
        Fall back to <title>, but only strip a trailing ' | Site Name' /
        ' - Site Name' suffix rather than picking the longest '-'-delimited
        chunk (which wrongly mangles titles that legitimately contain a
        hyphen or pipe as punctuation, e.g. 'Live: Team A - Team B recap')."""
        h1 = doc.xpath("//h1/text()")
        if h1 and h1[0].strip():
            return h1[0].strip()

        t = doc.xpath("//title/text()")
        if not t:
            return ""
        title = t[0].strip()
        # Only trim a short trailing site-name suffix (e.g. "Headline | CNN"),
        # identified as the last segment being short relative to the rest.
        for delim in [" | ", " - ", " — ", " » "]:
            if delim in title:
                head, _, tail = title.rpartition(delim)
                if head and len(tail) <= 40 and len(head) > len(tail):
                    title = head.strip()
                break
        return title

    def _authors_from_byline(self, doc) -> List[str]:
        byline = doc.xpath('//*[contains(@class, "byline") or contains(@class, "author")]//text()')
        if not byline:
            return []
        txt = " ".join(byline).strip()
        parts = re.split(r"[·|,]|\sand\s|\set\s", txt, flags=re.I)
        cleaned = [_clean_author_name(p) for p in parts]
        return list(dict.fromkeys(p for p in cleaned if p))

    def _pubdate(self, doc, url):
        time_tags = doc.xpath("//time/@datetime")
        if time_tags:
            try:
                parsed = _valid_date(date_parser.parse(time_tags[0]))
                if parsed:
                    return parsed
            except Exception:
                pass
        if url:
            m = STRICT_DATE_REGEX.search(url)
            if m:
                try:
                    parsed = _valid_date(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
                    if parsed:
                        return parsed
                except Exception:
                    pass
        return None

    def _category_from_url(self, url) -> str:
        path = urlparse(url).path.strip("/")
        for seg in [s for s in path.split("/") if s]:
            if not seg.isdigit() and len(seg) > 2:
                return seg.replace("-", " ").title()
        return ""

    def _images(self, doc, top_node, url) -> List[str]:
        imgs = []
        if top_node is not None:
            for img in top_node.xpath(".//img"):
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if not src or _is_junk_image(src):
                    continue
                # Skip images explicitly marked tiny (icon-sized) via attrs.
                try:
                    w, h = int(img.get("width", 0) or 0), int(img.get("height", 0) or 0)
                    if 0 < w <= 32 and 0 < h <= 32:
                        continue
                except ValueError:
                    pass
                imgs.append(_absolutize(src, url))
        return list(dict.fromkeys(i for i in imgs if i))

    def _videos(self, doc, top_node) -> List[str]:
        if top_node is None:
            return []
        vids = []
        for iframe in top_node.xpath(".//iframe"):
            src = iframe.get("src", "")
            if any(p in src for p in VIDEO_PROVIDERS):
                vids.append(src)
        # Native <video> tags (self-hosted players), src attr or nested <source>
        for video in top_node.xpath(".//video"):
            src = video.get("src")
            if src:
                vids.append(src)
            for source in video.xpath(".//source"):
                s = source.get("src")
                if s:
                    vids.append(s)
        return list(dict.fromkeys(vids))
