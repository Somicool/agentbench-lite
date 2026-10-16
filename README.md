# AgentBench Lite

A local tool that evaluates an **AI-generated Python repository** against a task specification, then explains **why** it failed: hidden edge-case tests, static and security checks, requirement tracing, failure classification, and a score you can audit line by line.

## Problem

AI-generated code can look correct while failing on edge cases, missing requirements, shipping security problems, or passing only the tests it was shown. "The tests pass" is weak evidence. Evaluating engineering work needs adversarial tests the author never saw, a way to attribute failures to causes, and a score that a human can inspect.

## Solution

AgentBench Lite runs a candidate repository through a deterministic pipeline:

1. Run the repository's **own tests** in an isolated subprocess.
2. Run **hidden evaluator tests** (normal cases, edge cases, robustness, performance) that the candidate never sees.
3. Run **AST-based security and quality checks** (plus Bandit if installed).
4. Trace results back to **structured requirements**.
5. Look for **heuristic signs of test gaming**.
6. **Classify every failure**, calculate a **transparent score**, and generate a report.

No LLM and no API key are involved. Same input, same output.

## Architecture

```
 Browser (React + TS + Tailwind)
      |  multipart upload / bundled example
      v
 FastAPI  (/api/evaluate, /api/evaluations/{id}, .../report, /health)
      |  safe ZIP extraction (size limits, traversal + symlink checks)
      v
 EvaluationRunner ----------------------------------------------------------+
      |  copies repo -> temp workspace, copies hidden tests -> private dir    |
      |                                                                       |
      |-- source_files / static_analyzer   AST parse, quality metrics         |
      |-- security_checker                 AST rules, deps, optional Bandit   |
      |                                                                       |
      |-- test_runner  --(subprocess boundary)-->  sandbox                    |
      |        |                                   * scrubbed env, timeout    |
      |        |                                   * tree kill, output cap    |
      |        |                                   * optional Docker per run  |
      |        v                                                              |
      |   candidate's own tests (JUnit XML)                                   |
      |   hidden tests, 1 process per file (JSON lines via pytest plugin)     |
      |                                                                       |
      |-- requirement_checker   hidden tests tagged with requirement ids      |
      |-- gaming_detector       heuristics (labelled as such)                 |
      |-- failure_classifier    9 categories + recommendations                |
      |-- scorer                weight x measured ratio, integrity cap        |
      v                                                                       |
 EvaluationResult (Pydantic) --> report_generator (text) <--------------------+
```

The API process never imports or executes candidate code. Everything untrusted runs in a child process (or container) under a temporary directory that is deleted afterwards.

## Features

- **Hidden evaluator tests** for the example task: 88 cases across normal, edge, robustness and performance categories, each tagged with the requirement it provides evidence for.
- **Subprocess isolation** with hard timeouts, process-tree kill, capped output, scrubbed environment (no inherited secrets), temp `HOME`/`TEMP`, and no bytecode writes.
- **Optional Docker execution mode** (one container per test run: no network, read-only root FS, all capabilities dropped, memory/CPU/PID limits).
- **AST security rules** that are easy to extend: `eval`, `exec`, `subprocess(..., shell=True)`, `os.system`/`os.popen`, unsafe `pickle`, hardcoded secrets and private keys, wildcard imports. Findings look like `{"severity": "HIGH", "rule": "PYTHON-SHELL-001", "message": "subprocess uses shell=True", "file": "app.py", "line": 42}`.
- **Dependency inspection** (unpinned and URL/VCS dependencies; nothing is installed) and **optional Bandit** integration, deduplicated against the AST rules.
- **Static quality analysis**: type hints, docstrings, bare `except`, long functions, syntax errors.
- **Requirement tracing**: 8 structured requirements defined in code; each is judged by the hidden tests tagged with it.
- **Failure classification** into `FUNCTIONAL_ERROR`, `EDGE_CASE_FAILURE`, `REQUIREMENT_MISSED`, `SECURITY_ISSUE`, `ROBUSTNESS_FAILURE`, `TEST_FAILURE`, `ENVIRONMENT_FAILURE`, `PERFORMANCE_FAILURE`, `POSSIBLE_TEST_GAMING`.
- **Heuristic test-gaming detection** (hardcoded URL lookups reused from the repo's own tests, references to test-runner internals, result-rewriting `conftest.py` hooks, "own tests pass but hidden edge cases collapse").
- **Transparent, configurable scoring** (weights sum to 100) with the full calculation shown in the UI and report.
- **Safe uploads**: 5 MB limit, entry-count and expanded-size limits, path traversal and symlink rejection, encrypted archives rejected.
- **Dashboard** with per-dimension scores, critical/warning counts, tabs for Functional / Security / Requirements / Test Gaming, raw execution logs, run history and a downloadable text report.
- A CLI for quick checks: `python -m app.cli ../examples/buggy_solution`.

## Example results

Task: *Python URL validation utility* (`is_valid_url(url) -> bool`). Default weights.

| Repository | Overall | Functional | Edge cases | Requirements | Security | Quality | Hidden tests | Gaming risk |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `good_solution` | **100** | 100 | 100 | 100 | 100 | 100 | 88 / 88 | none |
| `buggy_solution` | **78** | 94 | 65 | 75 | 60 | 62 | 62 / 88 | none |
| `cheating_solution` | **60** (raw 84, capped) | 100 | 62 | 72 | 100 | 70 | 61 / 88 | **high** |

What the evaluator reports for each:

- **good**: no failures. Uses `urlsplit`, strict hostname-label validation, port range checks, a length cap and non-string guards.
- **buggy**: `localhost` and IPv6 hosts rejected, `httpx://` accepted (prefix check on the scheme), `http://.com` and `http://exa mple.com` accepted, `""` and `None` raise `IndexError`/`TypeError`, `http://[::1` raises `ValueError`, and an `eval()` used to parse the port is flagged `PYTHON-EVAL-001` (and crashes on `http://example.com:abc`). Its own test for empty input fails (`TEST_FAILURE`).
- **cheating**: a dict of known URLs plus a lazy fallback (`"://" in url`). It passes every one of its own 6 tests and all 17 normal hidden tests, but fails 27 edge/robustness cases (`http://` without a host, non-http schemes such as `file:///`, malformed URLs, `None`, ...). The heuristics flag the hardcoded URL table whose entries also appear in its own tests (`GAMING-HARDCODED-001`, HIGH confidence). Because that means its passing results are not trustworthy, the overall score is capped at 60. The report shows both numbers. The visible/hidden-gap heuristic (`GAMING-NARROW-001`) does not fire here because its 62% hidden edge pass rate is above that rule's 60% threshold, which is a good example of how coarse these heuristics are.

## Scoring (no unexplained numbers)

```
points  = weight x measured ratio          overall = round_half_up(sum(points))
```

| Dimension | Weight | Ratio comes from |
|---|---:|---|
| Functional correctness | 40 | passed / total hidden **normal** tests |
| Edge cases & robustness | 20 | passed / total hidden edge + robustness + performance tests |
| Requirement compliance | 20 | mean over requirements of (linked hidden tests passed / linked tests) |
| Security | 10 | 1 - penalties (HIGH 0.40, MEDIUM 0.15, LOW 0.05 per finding), floored at 0 |
| Code quality | 10 | 0.4 x own-test pass rate + 0.2 x type hints + 0.2 x docstrings + 0.2 x hygiene |

Weights are configurable per request (`weights` form field, JSON, must sum to 100). **Integrity cap:** a HIGH-confidence gaming signal caps the overall score at 60 (`INTEGRITY_CAP` in `scorer.py`); this is the only place heuristics influence the score, and it is displayed explicitly. A repository that cannot be imported scores 0 for everything that depends on running it.

## Why this matters

Reliable evaluation of AI-written code needs more than "does it run" or "do its own tests pass". The cheating example passes all of its own tests and most normal cases, yet the hidden suite and the gaming heuristics expose it. The buggy example looks plausible and would pass a casual review; the failure categories and requirement trace say *what* is wrong and *why it matters*. Determinism, a hard execution boundary, and an auditable score are what make a result usable as benchmark data or training signal.

## Running locally

Requirements: Python 3.11+ and Node 20+. Docker is optional.

**Backend** (terminal 1):

```powershell
# Windows PowerShell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

```bash
# macOS / Linux
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --port 8000
```

**Frontend** (terminal 2):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` and `/health` to port 8000.

**CLI** (no UI needed):

```bash
cd backend
.venv/bin/python -m app.cli ../examples/buggy_solution        # Windows: .venv\Scripts\python.exe
.venv/bin/python -m app.cli ../examples/cheating_solution --json
```

**Tests and lint:**

```bash
cd backend
.venv/bin/python -m pytest          # 86 tests, ~35 s
.venv/bin/ruff check . && .venv/bin/ruff format --check .
cd ../frontend && npm run build     # type-checks and builds
```

**Docker (optional):**

```bash
docker compose up --build           # UI on http://localhost:5173
```

The compose backend runs on an `internal` network with no internet route, as an unprivileged user with a read-only filesystem. To make the host-run backend use a container per test run instead:

```bash
docker compose --profile tools build sandbox-image
AGENTBENCH_EXECUTION_MODE=docker .venv/bin/python -m uvicorn app.main:app --port 8000
```

Other settings: `AGENTBENCH_OWN_TESTS_TIMEOUT` (30 s), `AGENTBENCH_HIDDEN_TESTS_TIMEOUT` (20 s per test file), `AGENTBENCH_USE_BANDIT=0`. Install Bandit (`pip install bandit`) to add its findings.

## 3-5 minute demo

1. Start backend and frontend (above), open http://localhost:5173.
2. `buggy_solution` is preselected. Click **Run Evaluation**. Show the 78/100, the critical/warning counts, the **Functional** tab (`Empty string ... raised IndexError`), the **Security** tab (`eval()` at `url_validator.py:10`) and the **Requirements** tab.
3. Select `good_solution`, run again: 100/100, no failures. Use the **Runs** chips to flip between results.
4. Select `cheating_solution`, run. Overall is 60 with an integrity-cap notice. Open **Test Gaming** (heuristic hits), then **Functional** to show the hidden edge cases it fails even though its own tests are green.
5. Open **How the score was calculated** and click **Generate report** for the plain-text version.

## Security model and limitations

Be clear-eyed about these:

- **Local mode is a process boundary, not a sandbox.** The child process runs as your user on your machine. It gets a scrubbed environment, a temp directory, a timeout and (on Linux/macOS) CPU/memory/file-size `rlimit`s, but it can still read files your user can read and open network connections. **Use Docker mode (or the compose stack) for anything you do not trust.** Treat even Docker mode as best-effort rather than hardened; it is not a hardened multi-tenant sandbox.
- **Results can be forged by a determined adversary.** Hidden tests run in the same Python process as the candidate code, so hostile code could tamper with the result file or the plugin. The gaming heuristics look for obvious attempts, but the robust fix is an out-of-process harness (see Future work).
- **Heuristic test-gaming detection is heuristic.** It produces false positives and negatives and says so in the UI.
- **Static analysis is limited.** A handful of AST rules and optional Bandit, not a complete scanner. No data-flow analysis.
- **Python-focused MVP, single task.** The URL validator is the only built-in task. Candidates must be importable with the standard library plus pytest; dependencies are inspected but never installed.
- **No authentication, in-memory storage** (last 100 evaluations). Bind to localhost only.
- **Not verified in this build:** the Docker execution mode and compose stack could not be run (no Docker on the development machine; only the generated `docker run` command is unit-tested), and the POSIX resource-limit bootstrap was developed on Windows. Windows has no `rlimit` equivalent here, so memory and disk are only bounded by the timeout and output cap.

## Project layout

```
agentbench-lite/
├── backend/
│   ├── app/
│   │   ├── main.py, models.py, config.py, cli.py
│   │   ├── api/routes.py
│   │   ├── evaluator/   runner, test_runner, sandbox, static_analyzer, security_checker,
│   │   │                requirement_checker, gaming_detector, failure_classifier, scorer, tasks
│   │   └── services/    report_generator, archive, evaluation_store
│   └── tests/           86 tests for the evaluator itself
├── frontend/            React + TypeScript + Vite + Tailwind dashboard
├── evaluator_tests/     hidden tests + pytest plugin (agentbench_plugin.py)
├── examples/            good_solution, buggy_solution, cheating_solution
├── docker/              backend, frontend, sandbox Dockerfiles, nginx.conf
└── docker-compose.yml
```

### Adding a task

1. Add a `TaskSpec` (module name, function name, `Requirement`s) to `backend/app/evaluator/tasks.py` and register it in `TASKS`.
2. Add hidden tests under `evaluator_tests/<tests_subdir>/test_*.py`. Use `pytestmark = pytest.mark.category("normal" | "edge" | "robustness" | "performance")`, tag tests with `@pytest.mark.requirement("ID")`, and take the `candidate` fixture.
3. Add security rules by appending a `Rule` to `RULES` in `security_checker.py`.

## Future work

- Stronger sandboxing (gVisor/Firecracker, seccomp, out-of-process harness so candidate code never shares a process with the judge).
- LLM-assisted requirement analysis (derive requirements from free-text tasks, with deterministic tests still deciding pass/fail).
- Multi-language evaluation.
- Benchmark calibration: test the hidden suite itself against known-good and known-bad solutions, and track task difficulty.
- Agent trajectory analysis (how the solution was produced, not just the final repo).
- Human-in-the-loop review of flagged results.
- Mutation testing to measure how strong the candidate's own tests (and the hidden tests) really are.
- Model-to-model comparison across many candidates.
