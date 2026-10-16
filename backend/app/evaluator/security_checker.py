"""Rule-based security checks for candidate repositories.

This is a small, readable set of AST rules plus basic dependency inspection. It is NOT a
complete security scanner: it finds a handful of well-known dangerous patterns only.
Bandit is used as an extra source of findings when it happens to be installed.

To add a rule, write a function ``(node) -> message | None`` and append a ``Rule`` to ``RULES``.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from app.evaluator.sandbox import build_env
from app.evaluator.source_files import ParsedFile
from app.models import Finding, Severity

NodeCheck = Callable[[ast.AST], str | None]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: Severity
    recommendation: str
    check: NodeCheck


def _call_name(node: ast.AST) -> str | None:
    """Dotted name of the callee, e.g. 'os.system', or None for dynamic callees."""
    if not isinstance(node, ast.Call):
        return None
    parts: list[str] = []
    target = node.func
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
        return ".".join(reversed(parts))
    return None


def _check_eval(node: ast.AST) -> str | None:
    return "use of eval()" if _call_name(node) in {"eval", "builtins.eval"} else None


def _check_exec(node: ast.AST) -> str | None:
    return "use of exec()" if _call_name(node) in {"exec", "builtins.exec"} else None


def _check_shell_true(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    for keyword in node.keywords:
        if (
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
        ):
            return "subprocess uses shell=True"
    return None


def _check_os_system(node: ast.AST) -> str | None:
    name = _call_name(node)
    return f"{name}() runs a shell command" if name in {"os.system", "os.popen"} else None


def _check_pickle(node: ast.AST) -> str | None:
    name = _call_name(node)
    unsafe = {"pickle.load", "pickle.loads", "pickle.Unpickler", "cPickle.load", "cPickle.loads"}
    return (
        f"{name}() can execute arbitrary code when loading untrusted data"
        if name in unsafe
        else None
    )


_SECRET_NAME = re.compile(r"(password|passwd|secret|api_?key|token|private_?key|access_?key)", re.I)
_PLACEHOLDER = re.compile(r"(change.?me|your[-_ ]|example|placeholder|xxx|<.*>|\*{3,})", re.I)
_SECRET_VALUE = re.compile(r"(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")


def _assignment_targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return []
    return [t.id for t in targets if isinstance(t, ast.Name)]


def _check_hardcoded_secret(node: ast.AST) -> str | None:
    value = getattr(node, "value", None)
    if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
        return None
    text = value.value
    if len(text) < 8 or _PLACEHOLDER.search(text):
        return None
    for name in _assignment_targets(node):
        if _SECRET_NAME.search(name):
            return f"possible hardcoded secret assigned to '{name}'"
    return None


def _check_secret_literal(node: ast.AST) -> str | None:
    is_text = isinstance(node, ast.Constant) and isinstance(node.value, str)
    if is_text and _SECRET_VALUE.search(node.value):
        return "string literal looks like a cloud key or private key"
    return None


def _check_wildcard_import(node: ast.AST) -> str | None:
    if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
        return f"wildcard import from '{node.module or '.'}'"
    return None


RULES: tuple[Rule, ...] = (
    Rule(
        "PYTHON-EVAL-001",
        Severity.HIGH,
        "Remove eval(); parse the data explicitly (e.g. int(), json.loads, ast.literal_eval).",
        _check_eval,
    ),
    Rule("PYTHON-EXEC-001", Severity.HIGH, "Remove exec(); it runs arbitrary code.", _check_exec),
    Rule(
        "PYTHON-SHELL-001",
        Severity.HIGH,
        "Pass an argument list to subprocess and leave shell=False.",
        _check_shell_true,
    ),
    Rule(
        "PYTHON-OSSYSTEM-001",
        Severity.HIGH,
        "Use subprocess.run with an argument list instead of os.system().",
        _check_os_system,
    ),
    Rule(
        "PYTHON-PICKLE-001",
        Severity.MEDIUM,
        "Do not unpickle untrusted data; use JSON or another data-only format.",
        _check_pickle,
    ),
    Rule(
        "PYTHON-SECRET-001",
        Severity.HIGH,
        "Load secrets from environment variables or a secret store, not source code.",
        _check_hardcoded_secret,
    ),
    Rule(
        "PYTHON-SECRET-002",
        Severity.HIGH,
        "Remove embedded credentials from the repository and rotate them.",
        _check_secret_literal,
    ),
    Rule(
        "PYTHON-IMPORT-001",
        Severity.LOW,
        "Import only the names you need instead of using 'from x import *'.",
        _check_wildcard_import,
    ),
)


def scan_security(files: list[ParsedFile], rules: tuple[Rule, ...] = RULES) -> list[Finding]:
    """Run every rule over every parsed file and return findings in a stable order."""
    findings: list[Finding] = []
    for parsed in files:
        if parsed.tree is None:
            continue
        for node in ast.walk(parsed.tree):
            for rule in rules:
                message = rule.check(node)
                if message:
                    findings.append(
                        Finding(
                            severity=rule.severity,
                            rule=rule.rule_id,
                            message=message,
                            file=parsed.path,
                            line=getattr(node, "lineno", None),
                            recommendation=rule.recommendation,
                        )
                    )
    findings.sort(key=lambda f: (f.file, f.line or 0, f.rule))
    return findings


# --- dependency inspection -------------------------------------------------------------

_REQUIREMENT_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(.*)$")


def _parse_requirements_file(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [
        line.split("#", 1)[0].strip()
        for line in lines
        if line.split("#", 1)[0].strip() and not line.lstrip().startswith("-")
    ]


def _parse_pyproject_dependencies(path: Path) -> list[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
    except tomllib.TOMLDecodeError:
        return []
    deps = data.get("project", {}).get("dependencies", [])
    return [d for d in deps if isinstance(d, str)]


def _dependency_findings(spec: str, source_file: str) -> list[Finding]:
    if re.match(r"^(git\+|https?://|file:)", spec) or " @ " in spec:
        return [
            Finding(
                severity=Severity.MEDIUM,
                rule="DEPENDENCY-002",
                message=f"dependency installed from a URL or VCS: {spec}",
                file=source_file,
                recommendation="Depend on pinned releases from a package index.",
            )
        ]
    match = _REQUIREMENT_LINE.match(spec)
    if match and "==" not in match.group(2):
        return [
            Finding(
                severity=Severity.LOW,
                rule="DEPENDENCY-001",
                message=f"dependency '{match.group(1)}' is not pinned to an exact version",
                file=source_file,
                recommendation="Pin dependencies with == for reproducible evaluation.",
            )
        ]
    return []


def inspect_dependencies(root: Path) -> tuple[list[str], list[Finding]]:
    """List declared dependencies and flag unpinned or URL-based ones. Nothing is installed."""
    dependencies: list[str] = []
    findings: list[Finding] = []
    sources: list[tuple[str, list[str]]] = []
    for name in ("requirements.txt", "pyproject.toml"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            parse = (
                _parse_requirements_file if name.endswith(".txt") else _parse_pyproject_dependencies
            )
            sources.append((name, parse(path)))
    for source_file, specs in sources:
        for spec in specs:
            dependencies.append(spec)
            findings += _dependency_findings(spec, source_file)
    return dependencies, findings


# --- optional Bandit -------------------------------------------------------------------

_BANDIT_SEVERITY = {"HIGH": Severity.HIGH, "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW}


def bandit_available() -> bool:
    return find_spec("bandit") is not None


def run_bandit(root: Path, scratch: Path, timeout: float) -> list[Finding]:
    """Run Bandit over the sources (it reads files, it does not execute them)."""
    command = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        ".",
        "-f",
        "json",
        "-q",
        "-x",
        "./tests,./test,./.venv",
        "-s",
        "B101",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=build_env(scratch),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        report = json.loads(completed.stdout.decode("utf-8", errors="replace"))
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return []
    findings = []
    for issue in report.get("results", []):
        path = Path(issue.get("filename", "")).as_posix().removeprefix("./")
        findings.append(
            Finding(
                severity=_BANDIT_SEVERITY.get(issue.get("issue_severity", ""), Severity.LOW),
                rule=f"BANDIT-{issue.get('test_id', '?')}",
                message=issue.get("issue_text", "bandit finding"),
                file=path,
                line=issue.get("line_number"),
            )
        )
    return findings


def merge_findings(primary: list[Finding], extra: list[Finding]) -> list[Finding]:
    """Add extra findings, dropping ones that point at a line the primary rules already flagged."""
    seen = {(f.file, f.line) for f in primary if f.line is not None}
    merged = [*primary, *(f for f in extra if (f.file, f.line) not in seen)]
    merged.sort(key=lambda f: (f.file, f.line or 0, f.rule))
    return merged
