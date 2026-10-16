"""URL validation utility: accepts only well-formed HTTP and HTTPS URLs."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = frozenset({"http", "https"})

_UNSAFE_CHARS = re.compile(r"[\x00-\x20\x7f]")  # whitespace and control characters
_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_NUMERIC_HOST = re.compile(r"[0-9.]+")


def _is_valid_hostname(hostname: str) -> bool:
    if ":" in hostname:  # IPv6 literal; urlsplit strips the brackets
        try:
            ipaddress.IPv6Address(hostname)
        except ValueError:
            return False
        return True
    if _NUMERIC_HOST.fullmatch(hostname):  # looks like IPv4, so it must really be one
        try:
            ipaddress.IPv4Address(hostname)
        except ValueError:
            return False
        return True
    name = hostname.removesuffix(".")  # a single trailing dot is a valid FQDN
    if not name or len(name) > 253:
        return False
    return all(_HOST_LABEL.fullmatch(label) for label in name.split("."))


def is_valid_url(url: str) -> bool:
    """Return True if ``url`` is a well-formed http(s) URL with a hostname.

    Never raises: non-string input, empty input and parser errors all return False.
    """
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        return False
    if _UNSAFE_CHARS.search(url):
        return False
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        _ = parts.port  # raises ValueError for non-numeric or out-of-range ports
    except ValueError:
        return False
    if parts.scheme not in ALLOWED_SCHEMES or not hostname:
        return False
    return _is_valid_hostname(hostname)
