from __future__ import annotations

import ast

from app.evaluator.security_checker import (
    RULES,
    Rule,
    inspect_dependencies,
    merge_findings,
    scan_security,
)
from app.evaluator.source_files import parse_source
from app.models import Finding, Severity
from tests.helpers import write_repo


def scan(source: str, path: str = "app.py") -> list[Finding]:
    return scan_security([parse_source(path, source)])


def rules_found(source: str) -> set[str]:
    return {f.rule for f in scan(source)}


def test_eval_is_detected_with_location():
    findings = scan("x = 1\ny = eval(input())\n", "validator.py")
    assert [(f.rule, f.severity, f.file, f.line) for f in findings] == [
        ("PYTHON-EVAL-001", Severity.HIGH, "validator.py", 2)
    ]


def test_exec_is_detected():
    assert "PYTHON-EXEC-001" in rules_found("exec('print(1)')")


def test_subprocess_shell_true_is_detected():
    findings = scan("import subprocess\nsubprocess.run('ls', shell=True)\n")
    assert findings[0].rule == "PYTHON-SHELL-001"
    assert findings[0].message == "subprocess uses shell=True"
    assert findings[0].line == 2


def test_subprocess_without_shell_is_clean():
    assert scan("import subprocess\nsubprocess.run(['ls'], shell=False)\n") == []


def test_os_system_is_detected():
    assert "PYTHON-OSSYSTEM-001" in rules_found("import os\nos.system('rm -rf /')\n")


def test_pickle_load_is_detected():
    assert "PYTHON-PICKLE-001" in rules_found("import pickle\npickle.loads(blob)\n")


def test_hardcoded_secret_is_detected_but_placeholder_is_not():
    assert "PYTHON-SECRET-001" in rules_found("API_KEY = 'sk-live-1234567890abcdef'\n")
    assert rules_found("API_KEY = 'your-api-key-here'\n") == set()
    assert rules_found("API_KEY = os.environ['API_KEY']\n") == set()


def test_private_key_literal_is_detected():
    assert "PYTHON-SECRET-002" in rules_found("KEY = '-----BEGIN RSA PRIVATE KEY-----'\n")


def test_wildcard_import_is_detected():
    findings = scan("from os.path import *\n")
    assert findings[0].rule == "PYTHON-IMPORT-001" and findings[0].severity == Severity.LOW


def test_clean_code_has_no_findings():
    assert scan("def add(a: int, b: int) -> int:\n    return a + b\n") == []


def test_rules_are_easy_to_extend():
    def no_print(node: ast.AST) -> str | None:
        is_print = isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"
        return "print() call" if is_print else None

    custom = Rule("CUSTOM-PRINT-001", Severity.LOW, "Use logging.", no_print)
    findings = scan_security([parse_source("a.py", "print('x')")], (*RULES, custom))
    assert [f.rule for f in findings] == ["CUSTOM-PRINT-001"]


def test_unparseable_files_are_skipped_not_fatal():
    assert scan("def broken(:\n") == []


def test_dependency_inspection_flags_unpinned_and_url_dependencies(tmp_path):
    repo = write_repo(
        tmp_path,
        {"requirements.txt": "requests\nflask==3.0.0\ngit+https://example.com/x.git\n# comment\n"},
    )
    dependencies, findings = inspect_dependencies(repo)
    assert dependencies == ["requests", "flask==3.0.0", "git+https://example.com/x.git"]
    assert sorted(f.rule for f in findings) == ["DEPENDENCY-001", "DEPENDENCY-002"]


def test_merge_findings_drops_duplicates_on_the_same_line():
    ours = [
        Finding(severity=Severity.HIGH, rule="PYTHON-EVAL-001", message="m", file="a.py", line=3)
    ]
    theirs = [
        Finding(severity=Severity.MEDIUM, rule="BANDIT-B307", message="m", file="a.py", line=3),
        Finding(severity=Severity.LOW, rule="BANDIT-B110", message="m", file="a.py", line=9),
    ]
    assert [f.rule for f in merge_findings(ours, theirs)] == ["PYTHON-EVAL-001", "BANDIT-B110"]
