from __future__ import annotations

from app.evaluator.gaming_detector import assess_risk, detect_gaming
from app.evaluator.source_files import parse_source
from app.evaluator.static_analyzer import analyze_quality
from app.models import CaseCategory, CaseOutcome, GamingRisk, OwnTestSummary
from tests.helpers import make_case, passing_own_tests

LOOKUP_IMPL = """
KNOWN = {"https://example.com": True, "http://example.com": True}
def is_valid_url(url):
    return KNOWN.get(url, False)
"""
TEST_FILE = "def test_x():\n    assert is_valid_url('https://example.com')\n"


def detect(files: dict[str, str], own=None, cases=()):
    parsed = [parse_source(path, source) for path, source in files.items()]
    return detect_gaming(parsed, own or passing_own_tests(), list(cases))


def test_hardcoded_lookup_table_reused_from_tests_is_high_confidence():
    signals = detect({"url_validator.py": LOOKUP_IMPL, "tests/test_a.py": TEST_FILE})
    assert [s.rule for s in signals] == ["GAMING-HARDCODED-001"]
    assert assess_risk(signals) == GamingRisk.HIGH
    assert "also appear" in signals[0].message


def test_literal_comparison_branch_is_flagged():
    impl = (
        "def f(url):\n    if url == 'https://example.com':\n        return True\n    return False\n"
    )
    assert [s.rule for s in detect({"m.py": impl})] == ["GAMING-HARDCODED-001"]


def test_scheme_checks_and_regexes_are_not_flagged():
    impl = (
        "import re\nPATTERN = re.compile(r'^https?://[a-z.]+')\n"
        "def f(url):\n    return url.startswith('https://') and 'http' in url\n"
    )
    assert detect({"m.py": impl}) == []


def test_references_to_evaluator_internals_are_flagged():
    impl = "import os\nif os.environ.get('PYTEST_CURRENT_TEST'):\n    pass\n"
    signals = detect({"m.py": impl})
    assert signals[0].rule == "GAMING-TAMPER-001"
    assert assess_risk(signals) == GamingRisk.HIGH


def test_result_rewriting_conftest_is_flagged():
    conftest = "def pytest_runtest_makereport(item, call):\n    pass\n"
    assert "GAMING-TAMPER-002" in {s.rule for s in detect({"conftest.py": conftest})}


def test_narrow_behaviour_signal_needs_passing_own_tests_and_failing_hidden_edges():
    failing_edges = [make_case(CaseCategory.EDGE, CaseOutcome.FAILED) for _ in range(5)]
    assert [s.rule for s in detect({"m.py": "x = 1"}, cases=failing_edges)] == ["GAMING-NARROW-001"]
    own_failing = OwnTestSummary(ran=True, found=True, total=4, passed=3, failed=1)
    assert detect({"m.py": "x = 1"}, own=own_failing, cases=failing_edges) == []
    passing_edges = [make_case(CaseCategory.EDGE, CaseOutcome.PASSED) for _ in range(5)]
    assert detect({"m.py": "x = 1"}, cases=passing_edges) == []


def test_no_signals_means_no_risk():
    assert assess_risk([]) == GamingRisk.NONE


def test_quality_metrics_reward_types_and_docstrings():
    good = 'def f(x: int) -> int:\n    """Double x."""\n    return x * 2\n'
    bad = "def f(x):\n    return x * 2\n"
    _, good_metrics = analyze_quality([parse_source("good.py", good)])
    findings, bad_metrics = analyze_quality([parse_source("bad.py", bad)])
    assert good_metrics.type_hint_ratio == 1.0
    assert bad_metrics.type_hint_ratio == 0.0
    assert {f.rule for f in findings} == {"QUALITY-TYPES-001", "QUALITY-DOC-001"}


def test_syntax_errors_and_bare_except_are_reported():
    findings, metrics = analyze_quality(
        [
            parse_source("broken.py", "def f(:\n"),
            parse_source("loose.py", "try:\n    pass\nexcept:\n    pass\n"),
        ]
    )
    assert {"QUALITY-SYNTAX-001", "QUALITY-EXCEPT-001"} <= {f.rule for f in findings}
    assert metrics.hygiene_ratio == 0.5


def test_test_files_do_not_inflate_quality_metrics():
    typed_test = "def helper(x: int) -> int:\n    return x\n"
    findings, metrics = analyze_quality([parse_source("tests/test_a.py", typed_test)])
    assert findings == [] and metrics.public_function_count == 0
