"""URL validator (first draft)."""

from urllib.parse import urlparse


def _port_of(netloc):
    host_port = netloc.rsplit("@", 1)[-1]
    if ":" not in host_port:
        return 80
    return eval(host_port.rsplit(":", 1)[1])


def is_valid_url(url):
    if url[0].isspace():
        return False
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http"):
        return False
    if "." not in parsed.netloc:
        return False
    return _port_of(parsed.netloc) > 0
