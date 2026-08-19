from src.normalization.names import normalize_name, loose_name
from src.normalization.text import normalize_categories
from src.normalization.urls import normalize_url, urls_equivalent, extract_domain


def test_http_vs_https_normalize_the_same():
    assert normalize_url("http://openai.com") == normalize_url("https://openai.com")


def test_www_vs_non_www_normalize_the_same():
    assert normalize_url("https://www.openai.com") == normalize_url("https://openai.com")


def test_trailing_slash_removed():
    assert normalize_url("https://openai.com/blog/") == normalize_url("https://openai.com/blog")


def test_fragment_removed():
    assert normalize_url("https://openai.com/blog#section-2") == normalize_url("https://openai.com/blog")


def test_tracking_params_stripped():
    dirty = "https://openai.com/blog?utm_source=twitter&utm_medium=social"
    assert normalize_url(dirty) == normalize_url("https://openai.com/blog")


def test_meaningful_query_params_preserved():
    url = normalize_url("https://www.youtube.com/watch?v=abc123")
    assert "v=abc123" in url


def test_canonical_domain_variants_are_equivalent():
    assert urls_equivalent("openai.com", "https://www.openai.com/")
    assert urls_equivalent("http://openai.com/", "https://openai.com")


def test_extract_domain():
    assert extract_domain("https://www.huggingface.co/models") == "huggingface.co"


def test_none_and_empty_url_handled():
    assert normalize_url(None) is None
    assert normalize_url("") is None


def test_name_normalization_case_insensitive():
    assert normalize_name("OpenAI") == normalize_name("openai") == normalize_name("OPENAI")


def test_name_normalization_strips_punctuation_and_spaces():
    assert normalize_name("Open AI") == normalize_name("OpenAI")


def test_loose_name_strips_corporate_suffixes():
    assert loose_name("OpenAI Inc.") == loose_name("OpenAI")


def test_normalize_categories_dedupes_and_lowercases():
    result = normalize_categories(["Tool", "tool", "AI Agent"])
    assert result == ["tool", "ai-agent"]
