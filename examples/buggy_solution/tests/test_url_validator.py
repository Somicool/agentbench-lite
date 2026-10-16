from url_validator import is_valid_url


def test_valid_http():
    assert is_valid_url("http://example.com") is True


def test_valid_https_with_path():
    assert is_valid_url("https://example.com/a/b?x=1") is True


def test_missing_scheme():
    assert is_valid_url("example.com") is False


def test_ftp_is_rejected():
    assert is_valid_url("ftp://example.com") is False


def test_empty_string():
    assert is_valid_url("") is False
