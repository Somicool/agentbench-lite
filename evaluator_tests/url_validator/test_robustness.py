"""Robustness hidden tests: hostile input must never crash or stall the validator."""

import time

import pytest

pytestmark = pytest.mark.category("robustness")

MAX_SECONDS = 1.0


@pytest.mark.requirement("NO_UNEXPECTED_EXCEPTIONS")
@pytest.mark.parametrize(
    "value",
    [None, 123, 4.5, [], {}, b"http://example.com", object()],
    ids=lambda value: type(value).__name__,
)
def test_non_string_input_returns_false(candidate, value):
    """Non-string input returns False instead of raising"""
    result = candidate(value)
    assert result is False, f"expected False for non-string input, got {result!r}"


@pytest.mark.requirement("NO_UNEXPECTED_EXCEPTIONS")
@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/<script>alert(1)</script>",
        "http://ex\u00e4mple.com",
        "https://example.com/\u65e5\u672c\u8a9e",
        "http://\x00example.com",
        "http://example.com/\x00",
        "http://example.com/%zz",
        "'; DROP TABLE urls;--",
        "http://example.com/\\",
        "\u202ehttp://example.com",
        "http://%00",
        "http://[",
        "http://]",
        "http://[::1",
        "%%%",
        "\ud800",
    ],
    ids=repr,
)
def test_special_characters_never_raise(candidate, url):
    """Special characters and broken syntax return a bool without raising"""
    result = candidate(url)
    assert type(result) is bool, f"expected a bool, got {result!r}"


@pytest.mark.requirement("NO_UNEXPECTED_EXCEPTIONS")
def test_very_long_input_returns_a_bool(candidate):
    """A 1 MB URL returns a bool without raising"""
    result = candidate("https://example.com/" + "a" * 1_000_000)
    assert type(result) is bool, f"expected a bool, got {result!r}"


@pytest.mark.category("performance")
@pytest.mark.requirement("NO_UNEXPECTED_EXCEPTIONS")
@pytest.mark.parametrize(
    "url",
    [
        "http://" + "a." * 50_000 + "com",
        "http://" + "a-" * 5_000 + "!",
        "https://example.com/" + "?" * 100_000,
    ],
    ids=["many-labels", "backtracking-bait", "long-query"],
)
def test_pathological_input_is_fast(candidate, url):
    """Pathological input is handled in under one second"""
    started = time.perf_counter()
    candidate(url)
    elapsed = time.perf_counter() - started
    assert elapsed < MAX_SECONDS, f"took {elapsed:.2f}s (limit {MAX_SECONDS}s)"


@pytest.mark.requirement("ACCEPTS_STRING")
def test_results_are_deterministic(candidate):
    """Same input gives the same answer on repeated calls"""
    inputs = ["https://example.com", "nonsense", "http://exa mple.com"]
    first = [candidate(url) for url in inputs]
    assert first == [candidate(url) for url in inputs], "results changed between calls"
