import pytest

from url_validator import is_valid_url


@pytest.mark.parametrize(
    "url",
    ["http://example.com", "https://example.com/a?b=1#c", "http://localhost:8000", "http://[::1]/"],
)
def test_accepts_valid_urls(url):
    assert is_valid_url(url) is True


@pytest.mark.parametrize(
    "url",
    ["", "   ", "example.com", "http://", "ftp://example.com", "http://exa mple.com", "http://x:99999"],
)
def test_rejects_invalid_urls(url):
    assert is_valid_url(url) is False


@pytest.mark.parametrize("value", [None, 42, b"http://example.com"])
def test_non_string_input_is_rejected(value):
    assert is_valid_url(value) is False


def test_very_long_url_is_rejected_quickly():
    assert is_valid_url("http://example.com/" + "a" * 100_000) is False
