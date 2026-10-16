"""Task specifications.

A TaskSpec is everything the evaluator needs to know about one task: the interface the
candidate must expose, the structured requirements, and where the hidden tests live.
To support a new task, add a TaskSpec to ``TASKS`` and a folder of hidden tests under
``evaluator_tests/<tests_subdir>/`` that tags each test with ``@pytest.mark.requirement``.
"""

from __future__ import annotations

from dataclasses import dataclass


class UnknownTaskError(KeyError):
    """Raised when a task id is not registered."""


@dataclass(frozen=True)
class Requirement:
    id: str
    description: str
    recommendation: str


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    title: str
    default_description: str
    module_name: str  # module the candidate must provide
    function_name: str  # callable the hidden tests import from that module
    tests_subdir: str
    requirements: tuple[Requirement, ...]


URL_VALIDATOR_DESCRIPTION = """\
Build a Python URL validation utility.

The function should:
- accept a URL string
- return whether the URL is valid
- support HTTP and HTTPS URLs
- reject malformed URLs
- reject URLs without a hostname
- handle empty input safely
- never raise an unexpected exception for normal invalid input

Interface: provide `is_valid_url(url: str) -> bool` in a module named `url_validator`
(at the repository root or under `src/`). URLs whose scheme is not http or https are
invalid. Non-string input such as None must return False rather than raise.
"""

URL_VALIDATOR = TaskSpec(
    task_id="url-validator",
    title="Python URL validation utility",
    default_description=URL_VALIDATOR_DESCRIPTION,
    module_name="url_validator",
    function_name="is_valid_url",
    tests_subdir="url_validator",
    requirements=(
        Requirement(
            "ACCEPTS_STRING",
            "Accepts a URL string and returns a bool",
            "Return a real bool (True/False) for every string input.",
        ),
        Requirement(
            "HTTP_SUPPORTED",
            "HTTP URLs are accepted",
            "Accept well-formed http:// URLs, including ports, paths and queries.",
        ),
        Requirement(
            "HTTPS_SUPPORTED",
            "HTTPS URLs are accepted",
            "Accept well-formed https:// URLs, including ports, paths and queries.",
        ),
        Requirement(
            "HOSTNAME_REQUIRED",
            "URLs without a valid hostname are rejected",
            "Validate the hostname separately: reject empty hosts and malformed labels.",
        ),
        Requirement(
            "MALFORMED_REJECTED",
            "Malformed URLs are rejected",
            "Reject missing schemes, bad separators, invalid ports and illegal characters.",
        ),
        Requirement(
            "UNSUPPORTED_SCHEMES_REJECTED",
            "Schemes other than http and https are rejected",
            "Compare the parsed scheme to an exact allow-list, not a prefix.",
        ),
        Requirement(
            "EMPTY_INPUT_SAFE",
            "Empty and whitespace-only input is handled safely",
            "Handle empty input safely by returning False before any parsing or indexing.",
        ),
        Requirement(
            "NO_UNEXPECTED_EXCEPTIONS",
            "Invalid input never raises an unexpected exception",
            "Catch parser errors and non-string input so the function never raises.",
        ),
    ),
)

TASKS: dict[str, TaskSpec] = {URL_VALIDATOR.task_id: URL_VALIDATOR}


def get_task(task_id: str) -> TaskSpec:
    try:
        return TASKS[task_id]
    except KeyError:
        raise UnknownTaskError(f"unknown task '{task_id}'") from None
