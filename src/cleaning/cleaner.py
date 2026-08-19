"""Text cleaning (spec section 17).

Deliberately conservative: strips markup/noise but preserves technical
content (version numbers, model/repo names) because over-aggressive cleaning
destroys exactly the signal entity resolution and classification need.
"""
from __future__ import annotations

import html
import re
import unicodedata

from bs4 import BeautifulSoup

_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_BOILERPLATE_PATTERNS = [
    re.compile(r"read more.*$", re.IGNORECASE),
    re.compile(r"click here.*$", re.IGNORECASE),
    re.compile(r"subscribe to our newsletter.*$", re.IGNORECASE),
    re.compile(r"the post .* appeared first on .*$", re.IGNORECASE),
    re.compile(r"this article was originally published.*$", re.IGNORECASE),
]

# Tracking / analytics query parameters stripped from any URL found in text.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src", "igshid",
}


def strip_html(raw: str) -> str:
    """Remove HTML/RSS markup while keeping the underlying text content."""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return text


def normalize_unicode(text: str) -> str:
    """Fix malformed/mixed unicode via NFKC normalization + entity unescape."""
    if not text:
        return ""
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return text


def collapse_whitespace(text: str) -> str:
    if not text:
        return ""
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def strip_boilerplate(text: str) -> str:
    for pattern in _BOILERPLATE_PATTERNS:
        text = pattern.sub("", text)
    return text.strip()


def clean_text(raw: str | None) -> str:
    """Full cleaning pipeline for a single free-text field (name/description).

    Order matters: strip HTML first (so entity-decoding boilerplate regexes
    operate on plain text), then normalize unicode, then boilerplate, then
    collapse whitespace last so earlier steps' artifacts get tidied up.
    """
    if not raw:
        return ""
    text = strip_html(raw)
    text = normalize_unicode(text)
    text = strip_boilerplate(text)
    text = collapse_whitespace(text)
    return text


def is_empty_description(text: str | None) -> bool:
    if text is None:
        return True
    stripped = clean_text(text)
    # A handful of near-empty placeholder descriptions seen in the wild.
    return stripped.lower() in {"", "n/a", "none", "no description", "no description provided."}
