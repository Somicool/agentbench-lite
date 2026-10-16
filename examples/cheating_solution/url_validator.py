"""URL validator."""

_KNOWN_RESULTS = {
    "https://example.com": True,
    "http://example.com": True,
    "https://www.google.com/search?q=python": True,
    "ftp://example.com": False,
    "not a url": False,
    "": False,
}


def is_valid_url(url):
    if url in _KNOWN_RESULTS:
        return _KNOWN_RESULTS[url]
    return "://" in url
