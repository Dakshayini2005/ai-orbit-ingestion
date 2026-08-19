from src.cleaning.cleaner import clean_text, is_empty_description, strip_html, collapse_whitespace


def test_strips_html_tags():
    # strip_html uses a space separator between tag boundaries, so adjacent
    # inline tags can yield double spaces; collapse_whitespace (tested below
    # and applied by clean_text) is what normalizes that for real usage.
    assert strip_html("<p>Hello <b>world</b></p>").split() == ["Hello", "world"]


def test_strips_script_and_style_tags():
    raw = "<div><script>alert(1)</script><style>.a{}</style>Real content</div>"
    result = strip_html(raw)
    assert "alert" not in result
    assert "Real content" in result


def test_collapses_excessive_whitespace():
    assert collapse_whitespace("Hello    world\n\n\n\nfoo") == "Hello world\n\nfoo"


def test_normalizes_html_entities():
    assert "&" in clean_text("Tom &amp; Jerry")
    assert "&amp;" not in clean_text("Tom &amp; Jerry")


def test_cleans_rss_style_markup():
    raw = "<p>New model release &mdash; see details.</p><p>Read more at our site.</p>"
    cleaned = clean_text(raw)
    assert "<p>" not in cleaned
    assert "New model release" in cleaned


def test_preserves_technical_terms_and_version_numbers():
    raw = "<p>Announcing GPT-4o and Llama-3.1-8B-Instruct v2.3</p>"
    cleaned = clean_text(raw)
    assert "GPT-4o" in cleaned
    assert "Llama-3.1-8B-Instruct" in cleaned
    assert "v2.3" in cleaned


def test_is_empty_description_detects_placeholders():
    assert is_empty_description(None) is True
    assert is_empty_description("") is True
    assert is_empty_description("N/A") is True
    assert is_empty_description("No description provided.") is True
    assert is_empty_description("A real, useful description.") is False


def test_malformed_unicode_normalizes_without_crashing():
    raw = "Caf\u00e9 \u2014 na\u00efve r\u00e9sum\u00e9"
    cleaned = clean_text(raw)
    assert "Caf" in cleaned
