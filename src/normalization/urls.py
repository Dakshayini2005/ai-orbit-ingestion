"""URL normalization (spec section 18).

Goal: two URLs that point at the "same" resource should normalize to an
identical string, WITHOUT discarding query parameters that change what the
resource actually is (e.g. a HuggingFace model path, a YouTube `v=` id).
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from src.cleaning.cleaner import TRACKING_PARAMS

# Query params that ARE semantically meaningful and must never be stripped,
# even though they look like they could be tracking noise.
_MEANINGFUL_PARAMS = {"v", "id", "q", "query", "model", "repo", "dataset"}


def normalize_url(raw_url: str | None) -> str | None:
    if not raw_url or not raw_url.strip():
        return None

    url = raw_url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parts = urlsplit(url)

    scheme = "https"  # http -> https treated as equivalent

    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parts.path or ""
    if path == "/":
        path = ""
    elif len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Strip known tracking params; keep everything else (including anything
    # in _MEANINGFUL_PARAMS) exactly as given, preserving order.
    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(query_pairs)

    # Fragments (#section) are dropped — they identify a location within a
    # page, not a different resource.
    fragment = ""

    return urlunsplit((scheme, netloc, path, query, fragment))


def extract_domain(raw_url: str | None) -> str | None:
    normalized = normalize_url(raw_url)
    if not normalized:
        return None
    return urlsplit(normalized).netloc


def urls_equivalent(a: str | None, b: str | None) -> bool:
    na, nb = normalize_url(a), normalize_url(b)
    return na is not None and na == nb
