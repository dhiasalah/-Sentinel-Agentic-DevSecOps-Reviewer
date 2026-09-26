# Week 2 · Step 2.1 — Semgrep scan → JSON → `Finding` models

## 🎯 Goal
Run a real security scanner (Semgrep) on a small, **deliberately vulnerable** app, then turn its raw JSON
into clean Python objects (`Finding`). This is Sentinel's core idea in action: **scanners detect, the AI
reasons**. The scanner finds the issues, and in step 2.3 the LLM will triage and explain these `Finding`s.

## 🧰 Tools in this step

### SAST (Static Application Security Testing)
- **What it is:** finding security bugs by **reading the source code**, without running it. Analogy: a
  proofreader who knows the 200 classic ways to write a dangerous sentence and underlines each one.
- **Why:** it catches SQL injection, command injection, unsafe deserialization and weak crypto **before**
  the code is merged, which is exactly Sentinel's job on a pull request.
- **Limit:** it only knows the patterns it has rules for, and it produces **false positives** (it flags
  code that is actually safe). That's why step 2.3 adds an LLM to triage.

### Semgrep
- **What it is:** a fast, open-source SAST tool. Its rules look like the code they match (for example,
  `subprocess.run(..., shell=True)`), so they're easy to read. Thousands of community rules live in the
  **Semgrep Registry**, grouped in **rulesets** like `p/python`. [Docs](https://semgrep.dev/docs/) · [Registry](https://semgrep.dev/r)
- **In Sentinel:** the "Code flaws" scanner in the agent pipeline. In week 5 it becomes an MCP tool the agents call.
- **`--json`**: instead of colored text for humans, Semgrep prints one JSON document for programs to read.

### Running tools in Docker (instead of installing them)
- You don't `pip install semgrep` on Windows. You run the **official Semgrep image** and **mount** your
  code into it. Analogy: instead of hiring the inspector permanently, you call one in, show them the
  folder through a window (**read-only** mount), and they leave when done (`--rm`).
- **Why:** the same command works on Windows, in CI and in the k3s cluster, and a scanner reading
  untrusted PR code can't modify your files. This is the start of the **sandbox** idea from week 6.

### Python `subprocess`
- **What it is:** the stdlib module to run another program (here, `docker`) from Python and capture its
  output. [Docs](https://docs.python.org/3/library/subprocess.html)

### Pydantic models (again)
- The same library as your `Settings`. A `BaseModel` class validates data and gives it a fixed shape.
  Each scanner (Semgrep, gitleaks, Trivy, Checkov) outputs different JSON, and you'll **normalize** them
  all into one `Finding` shape, so the LLM and the dashboard only ever deal with one format.

### How it connects
```
 evals/vulnerable-apps/flask-demo/   (deliberately bad code)
            │  mounted read-only at /src
            ▼
 python -m sentinel.scanners.semgrep ──subprocess──▶ docker run semgrep/semgrep ... --json /src
            ▲                                                      │
            └──────────── raw JSON (stdout) ◀──────────────────────┘
            │
            ▼
 parse_findings(raw) ──▶ [Finding(rule_id, severity, file, line, message, cwe), ...]
                                   └──▶ step 2.3: LLM triage
```

## 💻 Commands

### 0. Fix `.gitignore` first (this now matters)
You're about to create a **second** venv (`agents/.venv`). Root `.gitignore` line 2 still reads
`.venv/__pycache__/`. Split it into two lines:
```gitignore
.venv/
__pycache__/
```
And remove the unused `import os` from `apps/api/app/main.py`. Commit:
```powershell
git add .gitignore apps/api/app/main.py
git commit -m "chore: fix .gitignore rules and remove unused import"
```

### 1. Pull the Semgrep image
```powershell
docker pull semgrep/semgrep
```
Expected: `Status: Downloaded newer image for semgrep/semgrep:latest` (a few hundred MB, once).

### 2. Set up the `agents/` Python project
From the repo root:
```powershell
cd agents
python -m venv .venv
.\.venv\Scripts\Activate.ps1
New-Item requirements.txt, requirements-dev.txt
New-Item -ItemType Directory sentinel, sentinel/scanners, tests
New-Item sentinel/__init__.py, sentinel/models.py, sentinel/scanners/__init__.py, sentinel/scanners/semgrep.py
New-Item tests/__init__.py, tests/test_semgrep.py
```
`requirements.txt`:
```
pydantic
```
`requirements-dev.txt`:
```
-r requirements.txt
pytest
```
```powershell
pip install -r requirements-dev.txt
git check-ignore -v .venv/pyvenv.cfg
```
Expected: `Successfully installed pydantic-... pytest-...`, then `.gitignore:2:.venv/	agents/.venv/pyvenv.cfg`.
The second line proves your **root** rule (not luck) ignores the new venv.

`agents/` is a separate Python project from `apps/api/`: in week 3 it becomes the **worker**, its own
container with its own dependencies. The API never runs scanners itself.

## 🧩 Code, piece by piece

### 1. The deliberately vulnerable demo app (test target)
**Where:** new file `evals/vulnerable-apps/flask-demo/app.py` (create the folders). Delete `evals/.gitkeep`.

```python
# DELIBERATELY VULNERABLE: test target for Sentinel. Never run or deploy this.
import hashlib
import pickle
import sqlite3
import subprocess

from flask import Flask, request

app = Flask(__name__)
ADMIN_PASSWORD = "hunter2-not-a-real-secret"


@app.route("/user")
def get_user():
    user_id = request.args.get("id")
    conn = sqlite3.connect("app.db")
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return str(conn.execute(query).fetchall())


@app.route("/ping")
def ping():
    host = request.args.get("host")
    return subprocess.check_output(f"ping -c 1 {host}", shell=True)


@app.route("/load", methods=["POST"])
def load():
    return str(pickle.loads(request.data))


def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
```
Each function plants one classic bug:
- **SQL injection:** user input goes straight into the SQL string.
- **Command injection:** `shell=True` with user input, so `host=8.8.8.8; rm -rf /` runs.
- **Unsafe deserialization:** `pickle.loads` on request data can execute arbitrary code.
- **Weak hashing:** MD5 for passwords.
- **Debug mode exposed:** `debug=True` on `0.0.0.0` exposes Flask's interactive debugger to the network.
- **Hardcoded password.**

You never install Flask or run this file. Semgrep only *reads* it. The fake password deliberately doesn't
look like a real provider key (`sk_live_...`, `AIza...`). GitHub's **push protection** would block a push
containing a real-looking key, and it will be your gitleaks test data in week 5.

### 2. The common `Finding` model
**Where:** `agents/sentinel/models.py`

```python
from pydantic import BaseModel


class Finding(BaseModel):
    tool: str
    rule_id: str
    severity: str
    message: str
    file: str
    line: int
    cwe: list[str] = []
```
This is the one shape every scanner's output will be converted into. `tool` records who found it
(Semgrep now, gitleaks/Trivy/Checkov later), `file` + `line` point to the exact place (later used to
comment on the right line of the PR), and `cwe` is the standard vulnerability category (e.g. *CWE-89: SQL Injection*)
that the LLM and the dashboard can group by.

### 3. Run Semgrep from Python
**Where:** `agents/sentinel/scanners/semgrep.py`, at the top.

```python
import json
import subprocess
import sys
from pathlib import Path

from sentinel.models import Finding

SEMGREP_IMAGE = "semgrep/semgrep"


def run_semgrep(target: Path) -> dict:
    target = target.resolve()
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{target}:/src:ro",
        SEMGREP_IMAGE,
        "semgrep", "scan",
        "--config", "p/python",
        "--json", "--quiet", "--metrics=off",
        "/src",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"semgrep failed (exit {proc.returncode}): {proc.stderr[-500:]}")
    return json.loads(proc.stdout)
```
- The command is a **list**, not a string: Python passes each piece to Docker as-is, with no shell in between.
  That's why your folder name with a space (`master 2`) works. It's also the exact defense against the
  command injection you planted in the demo app: never build commands by formatting user input into a shell string.
- `-v {target}:/src:ro` mounts the folder **read-only**, so the scanner can look but not touch.
- `--metrics=off` stops Semgrep from sending usage data home. `--quiet` keeps progress text out of the output.
- `timeout=300`: a huge or malicious repo can't hang your worker forever.
- Semgrep exits with `0` even when it finds issues (it only uses a non-zero exit code for real errors), so non-zero → raise.
  Only the last 500 characters of stderr go in the error, so a giant log doesn't flood your error.

### 4. Normalize the raw JSON into `Finding`s
**Where:** same file, below `run_semgrep`.

```python
def parse_findings(raw: dict) -> list[Finding]:
    findings = []
    for result in raw.get("results", []):
        extra = result.get("extra", {})
        cwe = extra.get("metadata", {}).get("cwe", [])
        if isinstance(cwe, str):
            cwe = [cwe]
        findings.append(
            Finding(
                tool="semgrep",
                rule_id=result["check_id"],
                severity=extra.get("severity", "INFO"),
                message=extra.get("message", "").strip(),
                file=result["path"].removeprefix("/src/"),
                line=result["start"]["line"],
                cwe=cwe,
            )
        )
    return findings
```
Semgrep's JSON has a `results` list, and each item has `check_id` (the rule), `path`, `start.line` and an
`extra` block with `message`, `severity` (`ERROR` / `WARNING` / `INFO`) and `metadata`. Some rules give
`cwe` as a single string and others as a list, so you coerce it to a list. Real-world scanner output is
messy, and normalizing is where you absorb that. `removeprefix("/src/")` turns the path inside the
container back into a path relative to the repo.

Note: don't rely on `extra.lines` (the matched code). Without a Semgrep login it just says
`"requires login"`. When the LLM needs the code (step 2.3), you'll read those lines from the file yourself.

### 5. Make it runnable
**Where:** same file, at the bottom.

```python
if __name__ == "__main__":
    target = Path(sys.argv[1])
    findings = parse_findings(run_semgrep(target))
    for f in findings:
        print(f"[{f.severity:7}] {f.file}:{f.line}  {f.rule_id}")
    print(f"\n{len(findings)} findings")
```
`python -m sentinel.scanners.semgrep <folder>` runs this block. `{f.severity:7}` pads the severity to 7 characters so the columns line up.

### 6. Test the parser without Docker
**Where:** `agents/tests/test_semgrep.py`

```python
from sentinel.scanners.semgrep import parse_findings

SAMPLE = {
    "results": [
        {
            "check_id": "python.lang.security.audit.subprocess-shell-true",
            "path": "/src/app.py",
            "start": {"line": 24, "col": 12},
            "extra": {
                "message": "  shell=True is dangerous  ",
                "severity": "ERROR",
                "metadata": {"cwe": "CWE-78: OS Command Injection"},
            },
        }
    ]
}


def test_parse_findings_normalizes_semgrep_output():
    [finding] = parse_findings(SAMPLE)
    assert finding.tool == "semgrep"
    assert finding.file == "app.py"
    assert finding.line == 24
    assert finding.message == "shell=True is dangerous"
    assert finding.cwe == ["CWE-78: OS Command Injection"]


def test_parse_findings_handles_no_results():
    assert parse_findings({"results": []}) == []
```
The parser is **pure logic**, so you test it with a small hand-made sample: fast, no Docker, no network.
The sample deliberately includes the messy cases (a string `cwe`, whitespace in the message, the `/src/` prefix).
`[finding] = ...` also asserts there is **exactly one** result (it errors on 0 or 2).

## 📚 Key concepts
- **Normalization layer:** N scanners × 1 common model means the LLM prompt, the PR comment and the
  database only know `Finding`. Adding a scanner = writing one `parse_*` function.
- **CWE** (Common Weakness Enumeration): a standard catalog of bug *types* (CWE-89 SQLi, CWE-78 OS
  command injection, CWE-502 deserialization). [cwe.mitre.org](https://cwe.mitre.org/)
- **Unit vs integration test:** `test_semgrep.py` tests your parsing (unit). Running the real scan below checks
  that Docker + Semgrep + parsing work together (integration). In week 9 CI will run the unit tests on every push.

## 🔐 Security note
- **The code you scan is untrusted.** Here it's your demo, but in week 3 it's a stranger's PR. Hence the read-only mount,
  no shell, a timeout, and the scanner in a throwaway container.
- The scanner container still has **network access**, because it downloads the `p/python` rules. In week 5 you'll
  consider pinning rules locally, so scanners can run with `--network none`.
- **LLM data privacy (for step 2.3):** Gemini's free tier may use the data you send to improve Google's models. Only
  send **public or demo** code through Sentinel, never private or company code.

## ✅ Check it works
Unit tests (from `agents/`, venv active):
```powershell
python -m pytest -v
```
Expected: `2 passed`.

Real scan (from `agents/`):
```powershell
python -m sentinel.scanners.semgrep ..\evals\vulnerable-apps\flask-demo
```
Expected: roughly 5–8 lines like these (exact rule names depend on the current registry):
```
[ERROR  ] app.py:24  python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
[WARNING] app.py:29  python.lang.security.deserialization.pickle.avoid-pickle
[WARNING] app.py:33  python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-md5
[WARNING] app.py:37  python.flask.security.audit.debug-enabled.debug-enabled
...

6 findings
```
Check that your planted bugs show up, and note which ones **didn't** (the hardcoded password probably won't).
That gap is why Sentinel runs several scanners (gitleaks for secrets in week 5).

Optionally, look at the raw JSON to see what you're parsing (from the repo root):
```powershell
docker run --rm -v "${PWD}\evals\vulnerable-apps\flask-demo:/src:ro" semgrep/semgrep semgrep scan --config p/python --json --quiet --metrics=off /src > semgrep-raw.json
```
Open `semgrep-raw.json` in VS Code, look around, then **delete it** (don't commit scan output).

Commit (from repo root):
```powershell
git add agents evals
git status
git commit -m "feat(agents): semgrep scanner wrapper with normalized Finding model"
git push
```
In `git status`, check that there's **no** `agents/.venv` and no `semgrep-raw.json`.

## ➡️ Next step
**2.2: LLM router** (Gemini primary, Groq fallback). Tell Claude **"I finished step 2.1, please review"** and paste your scan output.
