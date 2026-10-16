"""Normal-case hidden tests: everyday URLs the validator must classify correctly."""

import pytest

pytestmark = pytest.mark.category("normal")


def expect(candidate, url, expected):
    result = candidate(url)
    assert result is expected, f"expected {expected}, got {result!r}"


@pytest.mark.requirement("ACCEPTS_STRING")
def test_returns_a_real_bool(candidate):
    """Returns a bool, not a truthy object"""
    assert type(candidate("https://example.com")) is bool
    assert type(candidate("nonsense")) is bool


@pytest.mark.requirement("HTTP_SUPPORTED")
@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://www.example.com/",
        "http://sub.domain.example.co.uk/a/b",
        "http://example.com:80/index.html",
        "http://localhost:8000/health",
        "http://192.168.1.1:8080/status",
    ],
)
def test_valid_http_urls_are_accepted(candidate, url):
    """Accepts a valid HTTP URL"""
    expect(candidate, url, True)


@pytest.mark.requirement("HTTPS_SUPPORTED")
@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://example.com/path/to/page",
        "https://example.com/search?q=python&page=2",
        "https://example.com/page#section",
        "https://example.com:8443/secure",
        "HTTPS://EXAMPLE.COM/Path",
    ],
)
def test_valid_https_urls_are_accepted(candidate, url):
    """Accepts a valid HTTPS URL"""
    expect(candidate, url, True)


@pytest.mark.requirement("MALFORMED_REJECTED")
@pytest.mark.parametrize("url", ["not a url", "hello", "just-some-text", "12345"])
def test_plain_text_is_rejected(candidate, url):
    """Rejects text that is obviously not a URL"""
    expect(candidate, url, False)
