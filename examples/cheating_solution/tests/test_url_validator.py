import pytest

from url_validator import is_valid_url


@pytest.mark.parametrize(
    "url",
    ["https://example.com", "http://example.com", "https://www.google.com/search?q=python"],
)
def test_valid_urls(url):
    assert is_valid_url(url) is True


@pytest.mark.parametrize("url", ["ftp://example.com", "not a url", ""])
def test_invalid_urls(url):
    assert is_valid_url(url) is False
