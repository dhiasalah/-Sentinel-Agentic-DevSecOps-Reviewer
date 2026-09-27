# Week 2 · Step 2.4 — CLI: `python -m sentinel scan <folder>`

## 🎯 Goal
One command that does everything, **Semgrep → AI triage → safety rules → report**:
```powershell
python -m sentinel scan ..\evals\vulnerable-apps\flask-demo
```
This is the **Week 2 deliverable**. It also prepares week 3 and week 9: robots (a GitHub worker, a CI
pipeline) will run this same command, so it must "talk" in a way robots understand, not just humans.

## 🧰 Tools in this step

### A CLI (command-line interface) with `argparse`
- **What it is:** the "menu" of your program. It reads what you type after the command (`scan`, the folder,
  options like `--format json`) and turns it into Python variables. It also creates `--help` for free.
- **Why `argparse`:** it's built into Python, so there's nothing to install.
  [Docs](https://docs.python.org/3/library/argparse.html)

### `python -m sentinel` and `__main__.py`
- **What it is:** `python -m sentinel` means "run the `sentinel` package". Python looks for a file called
  `sentinel/__main__.py` and runs it. It's the **front door** of your package.

### Exit codes: a traffic light for robots
- **What it is:** when a program finishes, it gives back a **number** to whoever started it. Humans don't see it,
  but robots (CI pipelines, scripts) only look at that number.
  - `0` = 🟢 all good
  - `1` = 🔴 "I found serious problems" → CI **blocks** the pull request
  - `2` = 🟠 "I **couldn't** do my job" (Docker off, AI down, bad answer)
- **The security angle, very important:** if Sentinel crashes but still returns `0`, the robot thinks
  "no problems" and **lets dangerous code in**. So a crash must **never** return `0`. That's "fail closed"
  again: when in doubt, the door stays locked.
- In PowerShell you see the last exit code with `$LASTEXITCODE`.

### stdout vs stderr: two different output pipes
- **stdout** = the **result** (the report). **stderr** = **messages about problems** (errors, logs).
- **Why separate them?** Later a robot will run `sentinel scan ... --format json > report.json`. Only stdout goes
  into the file. If an error message landed in stdout, `report.json` would be broken JSON.

```
you / CI robot
      │  python -m sentinel scan <folder> --format text|json --fail-on high
      v
 __main__.py ──> cli.main()
                   ├─ run_semgrep + parse_findings   (2.1)
                   ├─ triage (router + AI + checks)   (2.2, 2.3A)
                   ├─ policy (safety rules)            (2.3B, already inside triage)
                   ├─ report ──> stdout (text or JSON)
                   └─ exit code ──> 0 🟢 / 1 🔴 / 2 🟠
```

## 🧩 Code, piece by piece

### 1. The CLI module
**Where:** new file `agents/sentinel/cli.py`. Paste the 3 pieces in order.

**1a. Imports, exit codes, the "menu":**
```python
import argparse
import json
import logging
import sys
import traceback
from pathlib import Path

from sentinel.config import Settings
from sentinel.llm.router import build_router
from sentinel.models import TriagedIssue
from sentinel.policy import SEVERITY_ORDER, rank
from sentinel.scanners.semgrep import parse_findings, run_semgrep
from sentinel.triage import triage

EXIT_OK, EXIT_ISSUES, EXIT_ERROR = 0, 1, 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sentinel", description="Scan a folder and print a triaged security report.")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="scan a local folder")
    scan.add_argument("path", type=Path, help="folder to scan")
    scan.add_argument("--format", choices=["text", "json"], default="text", help="text for humans, json for robots")
    scan.add_argument("--fail-on", choices=SEVERITY_ORDER, default="high",
                      help="exit code 1 if an issue is at least this severe (default: high)")
    scan.add_argument("-v", "--verbose", action="store_true", help="show detailed logs")
    return parser.parse_args(argv)
```
- **Named exit codes** (`EXIT_ISSUES` instead of a bare `1`) make the code readable: you see the *meaning*.
- `add_subparsers` makes `scan` a **sub-command**. Later you can add `sentinel fix` or `sentinel serve`
  next to it, like `git commit` / `git push`.
- `choices=` refuses anything else: `--fail-on urgent` gives a clear error instead of a strange bug.
- `argv` parameter: in normal use it's `None` (argparse reads what you typed). In tests we pass a list, so
  we can test the menu without a terminal.

**1b. The report and the traffic light:**
```python
def render_text(issues: list[TriagedIssue], finding_count: int) -> str:
    if not issues:
        return "No issues found."
    lines = []
    for issue in issues:
        flag = "  (AI thinks: false positive)" if issue.false_positive else ""
        where = ", ".join(dict.fromkeys(f"{f.file}:{f.line}" for f in issue.findings))
        lines.append(f"[{issue.severity.upper():8}] {issue.title}{flag}")
        lines.append(f"  at:  {where}")
        for reason in issue.review_reasons:
            lines.append(f"  ⚠ needs human review: {reason}")
        lines.append(f"  why: {issue.explanation}")
        lines.append(f"  fix: {issue.fix}")
        lines.append("")
    lines.append(f"{finding_count} scanner findings -> {len(issues)} issues")
    return "\n".join(lines)


def render_json(issues: list[TriagedIssue]) -> str:
    return json.dumps([issue.model_dump() for issue in issues], indent=2, ensure_ascii=False)


def exit_code(issues: list[TriagedIssue], fail_on: str) -> int:
    if any(rank(issue.severity) <= rank(fail_on) for issue in issues):
        return EXIT_ISSUES
    return EXIT_OK
```
- `dict.fromkeys(...)` removes duplicate locations but **keeps the order** (it fixes the
  `app.py:24, app.py:24, app.py:24` from the Part A review).
- `render_json` uses `model_dump()`: Pydantic turns each issue into a plain dict, **including the real
  Semgrep findings and the review reasons**. This JSON is what the week 3 worker and the week 7 dashboard will use.
- `exit_code`: remember `rank` 0 = critical, 4 = info. So `rank(issue) <= rank("high")` means
  "critical **or** high". With the default `--fail-on high`, a medium MD5 alone won't block a PR, but an SQL
  injection will. Each team can choose its own level.
- These three are **pure functions**: data in, text/number out, no network, no Docker. That's why they're easy to test.

**1c. `main`: glue everything together, and never fail silently:**
```python
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        findings = parse_findings(run_semgrep(args.path))
        issues = triage(findings, args.path, build_router(Settings()))
    except Exception as e:
        print(f"sentinel: scan failed: {type(e).__name__}: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return EXIT_ERROR
    print(render_json(issues) if args.format == "json" else render_text(issues, len(findings)))
    return exit_code(issues, args.fail_on)
```
- **Quiet by default:** logs only show warnings (like "Gemini down, using Groq"). `-v` shows everything,
  including the full error details.
- **`except Exception` → `EXIT_ERROR`**: we normally avoid catching *every* error. But this is the **outermost**
  layer of the program, where the only job left is: "tell the robot clearly that the scan **failed**". Without
  this, Python would crash with code `1`, which means "issues found", and the robot couldn't tell
  "dangerous code" from "Docker was off".
- `file=sys.stderr`: the error goes to the **error pipe**, never mixed into the report.
- The report is only printed when **everything** worked. There are no half-reports.

### 2. The front door
**Where:** new file `agents/sentinel/__main__.py`:
```python
import sys

from sentinel.cli import main

sys.exit(main())
```
`sys.exit(number)` hands the exit code from `main()` back to whoever started the program (you or a CI robot).

### 3. Clean up `triage.py` (one entry point only)
**Where:** `agents/sentinel/triage.py`.
- **Delete** the whole `if __name__ == "__main__":` block at the bottom. The CLI replaces it.
- Then **delete** the imports that only that block used: `import sys`, `from sentinel.config import Settings`,
  `from sentinel.scanners.semgrep import parse_findings, run_semgrep`.
- **Replace** `from sentinel.llm.router import LLMRouter, build_router` with:
```python
from sentinel.llm.router import LLMRouter
```
Now `triage.py` only *triages*. It doesn't scan, read settings or print. Each file has one job, which makes each one
easy to test and reuse (the week 3 worker will call `triage()` directly).

### 4. Tests
**Where:** new file `agents/tests/test_cli.py`:
```python
import json

from sentinel.cli import EXIT_ISSUES, EXIT_OK, exit_code, parse_args, render_json, render_text
from sentinel.models import Finding, TriagedIssue


def make_issue(severity="high", reasons=None):
    finding = Finding(tool="semgrep", rule_id="r", severity="ERROR", message="m", file="app.py", line=24)
    return TriagedIssue(title="Command injection", severity=severity, false_positive=False,
                        explanation="e", fix="f", findings=[finding, finding], review_reasons=reasons or [])


def test_fails_when_an_issue_reaches_the_threshold():
    assert exit_code([make_issue("high")], fail_on="high") == EXIT_ISSUES


def test_passes_when_issues_are_below_the_threshold():
    assert exit_code([make_issue("medium")], fail_on="high") == EXIT_OK


def test_no_issues_passes():
    assert exit_code([], fail_on="info") == EXIT_OK


def test_text_report_shows_location_once_and_review_flags():
    text = render_text([make_issue(reasons=["possible prompt injection"])], finding_count=2)
    assert text.count("app.py:24") == 1
    assert "needs human review: possible prompt injection" in text
    assert "2 scanner findings -> 1 issues" in text


def test_json_report_is_valid_json():
    data = json.loads(render_json([make_issue()]))
    assert data[0]["severity"] == "high"
    assert data[0]["findings"][0]["line"] == 24


def test_default_fail_on_is_high():
    assert parse_args(["scan", "some/folder"]).fail_on == "high"
```
The tests check the **promises robots rely on**: the right exit code, JSON that really is JSON, and review flags
that are never lost in the report.

## 💻 Commands
From `agents/` with the venv active (Docker Desktop running):
```powershell
python -m pytest -q
```
Expected: `28 passed` (22 + 6).

```powershell
python -m sentinel --help
python -m sentinel scan ..\evals\vulnerable-apps\flask-demo
echo "exit code: $LASTEXITCODE"
```
Expected: the report (no `INFO:httpx` noise anymore), ending with `9 scanner findings -> 4 issues` (or 5), then
`exit code: 1` 🔴 (there's a critical/high issue).

Try the other lights:
```powershell
python -m sentinel scan ..\evals\vulnerable-apps\flask-demo --format json > report.json
python -m sentinel scan .\does-not-exist ; echo "exit code: $LASTEXITCODE"
```
- `report.json` holds clean JSON (open it in VS Code). Then **delete it**, because it doesn't belong in git.
- The missing folder prints `sentinel: scan failed: FileNotFoundError: ...` and `exit code: 2` 🟠, which is **not 0**.

## 📚 Key concepts
- **Exit codes are an API** for other programs. `0` must mean "checked, and it's clean", never "I don't know".
- **stdout = data, stderr = messages.** It keeps machine-readable output clean.
- **One job per file:** scanner, triage, policy and CLI are separate, so week 3 can reuse them without the CLI.

## 🔐 Security note
- **Fail closed at the edge:** the one place where catching *all* errors is right is the program's outermost
  layer, and only to return a clear **failure** code.
- **Worth thinking about:** with `--fail-on high`, a PR full of `medium` issues passes. Who should choose that
  level: the PR author, the repo owner, or Sentinel? (Hint: week 8 has a per-repo settings page, and a PR author
  shouldn't be able to lower the bar for their own PR.)

## ✅ Done when
- `28 passed`
- `flask-demo` → report + `exit code: 1`; a missing folder → `exit code: 2`.
- Week 2 deliverable ✅: "CLI tool that scans a local repo and prints a triaged report".

## ➡️ Next step
**Week 3: GitHub App.** Sentinel starts reacting to real pull requests. Tell Claude **"step 2.4 works"** and
paste the outputs.
