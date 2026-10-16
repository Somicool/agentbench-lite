"""Edge-case hidden tests: the inputs AI-generated solutions most often get wrong."""

import pytest

pytestmark = pytest.mark.category("edge")


def expect(candidate, url, expected):
    result = candidate(url)
    assert result is expected, f"expected {expected}, got {result!r}"


@pytest.mark.requirement("EMPTY_INPUT_SAFE")
def test_empty_string_is_rejected_safely(candidate):
    """Empty string is rejected without raising"""
    expect(candidate, "", False)


@pytest.mark.requirement("EMPTY_INPUT_SAFE")
@pytest.mark.parametrize("url", ["   ", "\t", "\n", " \t\r\n "])
def test_whitespace_only_is_rejected(candidate, url):
    """Whitespace-only input is rejected"""
    expect(candidate, url, False)


@pytest.mark.requirement("MALFORMED_REJECTED")
@pytest.mark.parametrize("url", ["example.com", "www.example.com/path", "//example.com"])
def test_missing_scheme_is_rejected(candidate, url):
    """URL without a scheme is rejected"""
    expect(candidate, url, False)


@pytest.mark.requirement("HOSTNAME_REQUIRED")
@pytest.mark.parametrize(
    "url",
    ["http://", "https://", "http:///path", "http://:8080", "https://?q=1", "http://user@/path"],
)
def test_missing_hostname_is_rejected(candidate, url):
    """URL without a hostname is rejected"""
    expect(candidate, url, False)


@pytest.mark.requirement("HOSTNAME_REQUIRED")
@pytest.mark.parametrize(
    "url", ["http://.com", "http://example..com", "http://-example.com", "http://999.1.1.1"]
)
def test_malformed_hostname_is_rejected(candidate, url):
    """Hostname with empty or illegal labels is rejected"""
    expect(candidate, url, False)


@pytest.mark.requirement("MALFORMED_REJECTED")
@pytest.mark.parametrize(
    "url",
    [
        "http:/example.com",
        "http//example.com",
        "http:example.com",
        "ht!tp://example.com",
        "http://exa mple.com",
        "http://example.com:abc",
        "http://example.com:99999",
        "https://exa<mple>.com",
    ],
)
def test_malformed_urls_are_rejected(candidate, url):
    """Structurally malformed URL is rejected"""
    expect(candidate, url, False)


@pytest.mark.requirement("UNSUPPORTED_SCHEMES_REJECTED")
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "mailto:user@example.com",
        "ws://example.com",
        "httpx://example.com",
        "httpfoo://example.com",
        "https+evil://example.com",
    ],
)
def test_unsupported_schemes_are_rejected(candidate, url):
    """Scheme other than http/https is rejected"""
    expect(candidate, url, False)


@pytest.mark.requirement("HTTP_SUPPORTED")
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://[::1]:8080/",
        "http://user:pass@example.com",
        "http://my-site.example.com",
    ],
)
def test_unusual_but_valid_http_urls_are_accepted(candidate, url):
    """Accepts unusual but valid HTTP URL"""
    expect(candidate, url, True)


@pytest.mark.requirement("HTTPS_SUPPORTED")
@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@example.com:8443/path",
        "https://xn--bcher-kva.example/",
        "https://example.com/%E2%9C%93?q=%20",
        "https://example.com?x=1",
        "https://[2001:db8::1]/",
    ],
)
def test_unusual_but_valid_https_urls_are_accepted(candidate, url):
    """Accepts unusual but valid HTTPS URL"""
    expect(candidate, url, True)
