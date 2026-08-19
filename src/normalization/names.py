"""Name normalization — feeds entity resolution stage 1 (exact normalized name).

`normalize_name("OpenAI") == normalize_name("openai") == normalize_name("OPENAI")`
and common corporate suffixes (Inc., Ltd., Labs, AI) are stripped in a
*separate* "loose" form so we can compare both strict and loose variants
without conflating "OpenAI" the company with "OpenAI Gym" the library.
"""
from __future__ import annotations

import re
import unicodedata

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_CORP_SUFFIXES = [
    r"\binc\.?$", r"\bllc\.?$", r"\bltd\.?$", r"\bcorp\.?$",
    r"\bco\.?$", r"\blabs?$", r"\btechnologies?$",
]


def normalize_name(name: str) -> str:
    """Strict normalization: lowercase, unicode-fold, strip non-alphanumerics.

    Used for exact-match comparison (stage 1 of entity resolution).
    """
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = _NON_ALNUM_RE.sub("", text)
    return text


_FUZZY_SEPARATOR_RE = re.compile(r"[^a-z0-9.]+")


def fuzzy_normalize(name: str) -> str:
    """Token-preserving normalization for fuzzy comparison.

    Unlike `normalize_name`, this keeps word boundaries as spaces instead of
    collapsing everything into one blob string. This matters: RapidFuzz's
    token_sort_ratio is a TOKEN-based algorithm — feed it a single
    separator-free blob and it degenerates into near character-level
    comparison, which scores model variants that differ only in size or
    version (e.g. "Qwen2.5-1.5B-Instruct" vs "Qwen2.5-7B-Instruct") as
    deceptively similar, since most characters still match. Preserving
    tokens lets the differing size/version token actually count.

    Decimal points are kept attached to digits (so "3.1" stays one token,
    not "3" and "1") since splitting version numbers apart destroys exactly
    the signal that distinguishes one release from another.
    """
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = _FUZZY_SEPARATOR_RE.sub(" ", text)
    return " ".join(text.split())


def loose_name(name: str) -> str:
    """Looser normalization that also drops common corporate suffixes.

    Used only as a *secondary* signal alongside fuzzy matching — never as
    the sole basis for a merge, since stripping suffixes can conflate
    distinct entities (e.g. "Anthropic" vs a hypothetical "Anthropic Labs").
    """
    text = name.lower().strip()
    for pattern in _CORP_SUFFIXES:
        text = re.sub(pattern, "", text).strip()
    return normalize_name(text)


def fuzzy_normalize(name: str) -> str:
    """Normalization for FUZZY comparison — deliberately different from
    normalize_name().

    normalize_name() strips every separator into one run-on blob, which is
    correct for exact-match comparison but WRONG for fuzzy comparison: fed
    a blob, RapidFuzz's token_sort_ratio degenerates into character-level
    similarity, so "Qwen2.5-1.5B-Instruct" vs "Qwen2.5-7B-Instruct" score
    ~93 (one digit differs in a 20-char blob) even though they are
    different model sizes. This function keeps word/version boundaries as
    spaces (and keeps decimal points inside version numbers, e.g. "3.1"
    stays one token) so token_sort_ratio actually compares tokens like
    "1.5b" vs "7b" as the distinct units they are.
    """
    if not name:
        return ""
    text = name.lower().strip()
    text = re.sub(r"[/_-]", " ", text)
    text = re.sub(r"[^a-z0-9. ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(name: str) -> list[str]:
    return [t for t in normalize_name(name).split() if t]
