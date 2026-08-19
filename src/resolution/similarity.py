"""Similarity primitives backing multi-stage entity resolution (spec sec. 19).

Confidence scale used throughout resolution:
    exact URL match        = 1.00
    exact normalized name  = 0.95
    strong alias match     = 0.92
    fuzzy high confidence  = 0.88
    semantic similarity    = 0.80
"""
from __future__ import annotations

from rapidfuzz import fuzz

from src.normalization.names import fuzzy_normalize, loose_name, normalize_name
from src.normalization.urls import urls_equivalent

CONFIDENCE_EXACT_URL = 1.00
CONFIDENCE_EXACT_NAME = 0.95
CONFIDENCE_ALIAS = 0.92
CONFIDENCE_FUZZY = 0.88
CONFIDENCE_SEMANTIC = 0.80


def exact_url_match(url_a: str | None, url_b: str | None) -> bool:
    if not url_a or not url_b:
        return False
    return urls_equivalent(url_a, url_b)


def exact_name_match(name_a: str, name_b: str) -> bool:
    return bool(normalize_name(name_a)) and normalize_name(name_a) == normalize_name(name_b)


def alias_match(name: str, aliases: list[str]) -> bool:
    target = normalize_name(name)
    return any(normalize_name(a) == target or loose_name(a) == loose_name(name) for a in aliases)


def loose_name_match(name_a: str, name_b: str) -> bool:
    """Direct stage-3 alias check between two ENTITY NAMES (not requiring a
    pre-populated aliases list): "OpenAI" and "OpenAI Inc." should resolve
    together per the spec's own stage-3 example, but a freshly-discovered
    entity has no aliases recorded yet — alias_match() alone can never fire
    for it. loose_name() already strips common corporate suffixes
    (Inc./LLC/Ltd./Corp./Labs/...), so comparing it directly between the two
    candidate names (rather than only against a maintained alias list)
    is what actually implements that spec example.
    """
    la, lb = loose_name(name_a), loose_name(name_b)
    return bool(la) and la == lb


def fuzzy_score(name_a: str, name_b: str) -> float:
    """0-100 RapidFuzz token-sort-ratio score.

    Uses fuzzy_normalize (token-preserving), NOT normalize_name — see that
    function's docstring for why feeding token_sort_ratio a separator-free
    blob defeats the point of a token-based algorithm.
    """
    return fuzz.token_sort_ratio(fuzzy_normalize(name_a), fuzzy_normalize(name_b))


def semantic_score_stub(name_a: str, name_b: str, description_a: str = "", description_b: str = "") -> float:
    """Lightweight stand-in for embedding-based semantic similarity.

    The spec makes embeddings OPTIONAL ("For ambiguous cases, optionally use
    embeddings... Do NOT require an external LLM for every comparison").
    Rather than pull in a heavyweight embedding dependency for this scale of
    project, this uses token-set overlap as a cheap semantic proxy, returned
    as a 0-1 score — intentionally the lowest-confidence, last-resort signal
    in the resolution pipeline.

    IMPORTANT: name overlap is the gate, description overlap is only a
    tie-breaker on top of it. Two records with generic, near-identical
    boilerplate descriptions (e.g. "text-generation model on Hugging Face"
    for every text-generation model) but completely different names must
    NOT be treated as semantically similar — description-only overlap
    caused exactly that false-positive merge in early testing. Requiring
    nonzero name-token overlap before description can contribute keeps the
    stage conservative, as the "last resort" signal should be.
    """
    def _tokens(text: str) -> set[str]:
        # Keep "." attached to digits (version numbers like "3.1" stay one
        # token). Split on "/" and "-" only. Minimum length 2 (not >3) so
        # short-but-critical distinguishing tokens like "8b", "7b" survive —
        # dropping them was the root cause of an earlier false-merge bug
        # where "Qwen3-8B" and "Qwen3-0.6B" looked identical once their
        # size suffixes were filtered out.
        cleaned = text.lower().replace("/", " ").replace("-", " ")
        return set(t for t in cleaned.split() if len(t) >= 2)

    name_tokens_a, name_tokens_b = _tokens(name_a), _tokens(name_b)
    if not name_tokens_a or not name_tokens_b:
        return 0.0

    name_overlap = len(name_tokens_a & name_tokens_b) / len(name_tokens_a | name_tokens_b)
    if name_overlap < 0.5:
        # Gate: require the MAJORITY of name tokens to overlap, not just
        # one shared word. A shared generic token ("model", "base") is not
        # enough on its own — that was the second half of the same bug:
        # "distilbert-base-uncased" and "bert-base-uncased" share "base"
        # and "uncased" but are different models.
        return 0.0

    desc_tokens_a = _tokens(description_a)
    desc_tokens_b = _tokens(description_b)
    desc_overlap = 0.0
    if desc_tokens_a and desc_tokens_b:
        desc_overlap = len(desc_tokens_a & desc_tokens_b) / len(desc_tokens_a | desc_tokens_b)

    return 0.7 * name_overlap + 0.3 * desc_overlap


_VARIANT_SIZE_WORDS = {
    "tiny", "mini", "small", "base", "medium", "large", "huge",
    "xl", "xxl", "xs", "xxs",
}

# Tokens safe to ignore when they're the ONLY difference between two names —
# these are corporate-suffix noise the spec explicitly wants tolerated
# ("OpenAI" / "OpenAI Inc." should still resolve together), not genuine
# product/model distinguishers.
_IGNORABLE_EXTRA_TOKENS = {"inc", "llc", "ltd", "corp", "co", "labs", "lab", "technologies", "technology"}


def _variant_tokens(name: str) -> set[str]:
    """Extract "variant-distinguishing" tokens from a name: anything
    containing a digit (model sizes like "8b", "0.6b", version numbers like
    "3.1", layer counts like "l4") plus common size words (small/base/
    large/...). These are exactly the tokens that separate genuinely
    different model releases that otherwise share almost every other token
    (e.g. "Qwen2.5-1.5B-Instruct" vs "Qwen2.5-7B-Instruct").
    """
    tokens = fuzzy_normalize(name).split()
    return {t for t in tokens if any(ch.isdigit() for ch in t) or t in _VARIANT_SIZE_WORDS}


def has_conflicting_variant_tokens(name_a: str, name_b: str) -> bool:
    """True if both names carry variant tokens (sizes/versions) and those
    token sets differ. See has_conflicting_tokens (below) for the more
    general version of this check — this narrower digit/size-word check is
    kept as an extra explicit safeguard for the most common case.
    """
    va, vb = _variant_tokens(name_a), _variant_tokens(name_b)
    return bool(va) and bool(vb) and va != vb


def has_conflicting_tokens(name_a: str, name_b: str) -> bool:
    """General guard: True if either name has a token the other lacks
    (ignoring corporate-suffix noise), and that extra token isn't itself a
    near-spelling-variant of something on the other side.

    Why this exists: token_sort_ratio-style fuzzy matching scores two names
    as highly similar whenever most tokens match, even when the ONE
    differing token is exactly what makes them different entities —
    "Qwen2.5-VL-7B-Instruct" (adds a vision-language modality tag) vs
    "Qwen2.5-7B-Instruct", or "xlm-roberta-base" (adds a multilingual
    variant prefix) vs "roberta-base". A single inserted/removed token that
    isn't a corporate suffix and isn't a typo of an existing token is
    treated as a hard block on fuzzy/semantic merging — real duplicates
    across sources don't gain or lose a whole extra word.
    """
    tokens_a = set(fuzzy_normalize(name_a).split())
    tokens_b = set(fuzzy_normalize(name_b).split())

    # Strip trailing periods ("inc." -> "inc") only for the purpose of
    # matching against the ignorable-suffix list — a trailing "." from an
    # abbreviation shouldn't defeat the "OpenAI Inc." == "OpenAI" case.
    only_a = {t.rstrip(".") for t in (tokens_a - tokens_b)} - _IGNORABLE_EXTRA_TOKENS
    only_b = {t.rstrip(".") for t in (tokens_b - tokens_a)} - _IGNORABLE_EXTRA_TOKENS

    if not only_a and not only_b:
        return False

    if len(only_a) != len(only_b):
        return True

    # Equal-sized leftover sets: allow it through only if every leftover
    # token on one side is a close spelling variant of some leftover token
    # on the other (typo-level), not a genuinely different word.
    for ta in only_a:
        best = max((fuzz.ratio(ta, tb) for tb in only_b), default=0)
        if best < 80:
            return True
    return False
