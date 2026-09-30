# Week 4 · Step 4.2 — A benchmark with planted vulnerabilities (Part A: the exam + the answer key)

## 🗺️ In plain words: what we're doing today

Right now we *feel* that Sentinel works, because it found 6 issues on PR #7. But we don't know **how many it missed**, or how many of
its warnings are wrong. Today we write a small **exam** for Sentinel: a fake app where **we** hide 15 known vulnerabilities and 4
"trick questions" (code that looks dangerous but is safe). We also write the **answer key** in a separate file. In Part B, a script
will grade Sentinel's report against the key and print a score.

**Example:** at the end of Part B you'll see something like `found 9/15 planted vulns (60%) · 1/4 decoys wrongly flagged`.
That line becomes the "detected X%" number in your CV bullet.

## 🎯 Goal

A **ground-truth benchmark** in `evals/benchmark/`, meaning a target folder plus an `expected.json` answer key. Every change to Sentinel
(new scanner, new prompt, new model) can then be **measured**, not guessed. In week 10 this runs in CI and gives the final numbers.

## 🧰 Tools in this step

- **Benchmark / ground truth**: like an exam with a hidden answer sheet. We plant the bugs ourselves, so we **know** the right
  answer, which is impossible on real code. It solves "is the new version better or worse?". Sentinel needs it because LLM output
  changes from run to run (remember MD5 was *medium* one day and *high* the next). It comes back in week 10 ("detection rate + false positives").
- **CWE (Common Weakness Enumeration)**: a catalog of bug *types* with numbers, like "CWE-89 = SQL injection".
  Scanners tag findings with CWEs, so it's a shared language to compare "what we planted" with "what was found". [Catalog](https://cwe.mitre.org/)
- **OWASP Benchmark** is the professional version of this idea (thousands of test cases, true and false). We build a tiny one we fully understand.
  [OWASP Benchmark](https://owasp.org/www-project-benchmark/)

```
evals/benchmark/
├── target/          ← Sentinel scans THIS folder (the exam paper)
│   ├── app/*.py         15 planted vulns + 4 decoys, no hints in the code
│   ├── Dockerfile       a container misconfiguration  (Checkov, week 5)
│   └── requirements.txt old vulnerable versions        (Trivy, week 5)
└── expected.json    ← answer key, OUTSIDE target/ so the AI never reads it
```

---

## 🧠 Three rules of a fair exam (read this before typing)

1. **No hints in the scanned code.** No `# VULN: SQL injection` comments, and no function names like `find_user_safe` or `insecure_hash`.
   The triage LLM **reads the code**. A hint would let it "cheat", and our score would measure our comments instead of Sentinel.
   This is called **data contamination**, and it's the #1 way AI evals lie. That's also why the answer key lives **outside** `target/`.
2. **Include decoys (true negatives).** If the exam only has bugs, a scanner that flags *every line* scores 100%. Decoys are safe code that
   *looks* scary (a parameterised SQL query, `subprocess` with a list). They measure **false positives**, the thing that makes developers
   ignore a bot.
3. **Plant things we know we'll miss today.** Semgrep with `p/python` won't see the Dockerfile or the old library versions. That's intended:
   the score must show the gap *now*, so week 5 (Checkov, Trivy, gitleaks) can prove it closes it.

---

## 🧩 Code, piece by piece

⚠️ **This code is deliberately insecure. Never run it, install its requirements, or deploy it.** It only exists to be *read* by scanners.
Type each file **exactly**, including blank lines: the answer key points to **line numbers**.

### 1. SQL: one injectable query, one safe decoy
**Where:** new file `evals/benchmark/target/app/db.py`
```python
import sqlite3


def find_user(conn: sqlite3.Connection, name: str):
    query = "SELECT id, email FROM users WHERE name = '%s'" % name
    return conn.execute(query).fetchone()


def find_user_by_email(conn: sqlite3.Connection, email: str):
    return conn.execute("SELECT id, name FROM users WHERE email = ?", (email,)).fetchone()
```
**V01** (line 5): the name is pasted into the SQL text, so `' OR '1'='1` changes the query. **D01** (line 10): the `?` placeholder sends the
value separately from the SQL, so it's safe. A scanner that flags both "because it's SQL" gets a false positive.

### 2. Files and processes
**Where:** new file `evals/benchmark/target/app/files.py`
```python
import os
import subprocess

UPLOAD_DIR = "/srv/uploads"


def read_upload(filename: str) -> bytes:
    with open(os.path.join(UPLOAD_DIR, filename), "rb") as f:
        return f.read()


def ping(host: str) -> str:
    return subprocess.check_output(f"ping -c 1 {host}", shell=True, text=True)


def traceroute(host: str) -> str:
    return subprocess.check_output(["traceroute", "--", host], text=True)
```
**V02** (line 8), path traversal: `filename = "../../etc/passwd"` escapes the folder, and `os.path.join` even drops `UPLOAD_DIR` if the name is absolute.
**V03** (line 13), command injection: `host = "x; rm -rf /"` runs a second command because `shell=True` hands the string to a shell.
**D02** (line 17): a list means no shell, and `--` stops `host` from being read as an option. This is the fix for V03, used as a decoy.

### 3. Crypto and secrets
**Where:** new file `evals/benchmark/target/app/crypto.py`
```python
import hashlib
import random
import string

SECRET_KEY = "s3nt1nel-benchmark-not-a-real-secret"


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def reset_token() -> str:
    return "".join(random.choice(string.ascii_letters) for _ in range(32))


def file_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
```
**V04** (line 5): a secret in source code. The value is obviously fake on purpose, because a realistic-looking key would be blocked by GitHub push
protection, or worse, mistaken for a real leak. **V05** (line 9): MD5 is fast to brute-force, so it's wrong for passwords (use bcrypt/argon2).
**V06** (line 13): `random` is predictable. Reset tokens need `secrets`. **D03** (line 17): SHA-256 for a *file checksum* is fine,
because the weakness depends on **what the hash is used for**, not on the function name.

### 4. Deserialisation
**Where:** new file `evals/benchmark/target/app/serialize.py`
```python
import pickle

import yaml


def load_session(blob: bytes):
    return pickle.loads(blob)


def load_config(text: str):
    return yaml.load(text, Loader=yaml.Loader)


def load_defaults(text: str):
    return yaml.safe_load(text)
```
**V07** (line 7): unpickling attacker bytes = running attacker code. Semgrep **missed pickle** in step 2.1, so this one tests a known blind spot.
**V08** (line 11): the full YAML `Loader` can build arbitrary Python objects. **D04** (line 15): `safe_load` only builds plain data.

### 5. Auth
**Where:** new file `evals/benchmark/target/app/auth.py`
```python
import jwt


def current_user(token: str) -> str:
    claims = jwt.decode(token, options={"verify_signature": False})
    return claims["sub"]
```
**V09** (line 5): without signature checking, anyone can write `{"sub": "admin"}` and be admin. It's the same JWT idea as your GitHub App (3.1),
seen from the attacker's side.

### 6. Web
**Where:** new file `evals/benchmark/target/app/web.py`
```python
import requests
from flask import Flask, redirect, render_template_string, request

app = Flask(__name__)


@app.route("/hello")
def hello():
    name = request.args.get("name", "")
    return render_template_string("<h1>Hello " + name + "</h1>")


@app.route("/fetch")
def fetch():
    return requests.get(request.args["url"], timeout=5).text


@app.route("/go")
def go():
    return redirect(request.args.get("next", "/"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
```
**V10** (line 10), server-side template injection: `name={{7*7}}` renders `49`, and worse payloads run code. **V11** (line 15), SSRF: the server fetches
*any* URL for the attacker, including `http://169.254.169.254/` (cloud metadata, where credentials live; this matters for your Oracle VM in week 9).
**V12** (line 20), open redirect: `?next=https://evil.example` is phishing with your domain's name on it. **V13** (line 24): the debug console = remote code execution.

### 7. The container
**Where:** new file `evals/benchmark/target/Dockerfile`
```dockerfile
FROM python:latest
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "app/web.py"]
```
**V14** (whole file): no `USER`, so it runs as root (compare with your API's Dockerfile from 1.3). The `latest` tag isn't reproducible either.
Semgrep `p/python` doesn't read Dockerfiles, so we **expect to miss this today**.

### 8. The dependencies
**Where:** new file `evals/benchmark/target/requirements.txt`
```
flask==0.12.2
pyyaml==5.3
requests==2.19.0
PyJWT==2.10.1
```
**V15** (lines 1–3): versions with published CVEs (for example PyYAML 5.3 → CVE-2020-1747, code execution). Your code can be perfect and still be
vulnerable through a library. That's **supply-chain** risk, and Trivy's job in week 5. Expect to miss this today too.
Since the repo is public, GitHub's **Dependabot** may open alerts for this file. That's expected: dismiss them as "used in tests".

### 9. The answer key
**Where:** new file `evals/benchmark/expected.json` (next to `target/`, **not inside it**)
```json
{
  "target": "target",
  "vulns": [
    {"id": "V01", "file": "app/db.py", "lines": [5, 6], "cwe": "CWE-89", "title": "SQL injection", "scanner": "semgrep"},
    {"id": "V02", "file": "app/files.py", "lines": [8, 8], "cwe": "CWE-22", "title": "Path traversal", "scanner": "semgrep"},
    {"id": "V03", "file": "app/files.py", "lines": [13, 13], "cwe": "CWE-78", "title": "OS command injection", "scanner": "semgrep"},
    {"id": "V04", "file": "app/crypto.py", "lines": [5, 5], "cwe": "CWE-798", "title": "Hardcoded secret", "scanner": "gitleaks"},
    {"id": "V05", "file": "app/crypto.py", "lines": [9, 9], "cwe": "CWE-328", "title": "Weak password hash (MD5)", "scanner": "semgrep"},
    {"id": "V06", "file": "app/crypto.py", "lines": [13, 13], "cwe": "CWE-338", "title": "Insecure random token", "scanner": "semgrep"},
    {"id": "V07", "file": "app/serialize.py", "lines": [7, 7], "cwe": "CWE-502", "title": "Unsafe pickle", "scanner": "semgrep"},
    {"id": "V08", "file": "app/serialize.py", "lines": [11, 11], "cwe": "CWE-502", "title": "Unsafe YAML load", "scanner": "semgrep"},
    {"id": "V09", "file": "app/auth.py", "lines": [5, 5], "cwe": "CWE-347", "title": "JWT signature not verified", "scanner": "semgrep"},
    {"id": "V10", "file": "app/web.py", "lines": [10, 10], "cwe": "CWE-1336", "title": "Server-side template injection", "scanner": "semgrep"},
    {"id": "V11", "file": "app/web.py", "lines": [15, 15], "cwe": "CWE-918", "title": "SSRF", "scanner": "semgrep"},
    {"id": "V12", "file": "app/web.py", "lines": [20, 20], "cwe": "CWE-601", "title": "Open redirect", "scanner": "semgrep"},
    {"id": "V13", "file": "app/web.py", "lines": [24, 24], "cwe": "CWE-489", "title": "Flask debug mode", "scanner": "semgrep"},
    {"id": "V14", "file": "Dockerfile", "lines": [1, 5], "cwe": "CWE-250", "title": "Container runs as root", "scanner": "checkov"},
    {"id": "V15", "file": "requirements.txt", "lines": [1, 3], "cwe": "CWE-1395", "title": "Vulnerable dependencies", "scanner": "trivy"}
  ],
  "decoys": [
    {"id": "D01", "file": "app/db.py", "lines": [10, 10], "why_safe": "parameterised query"},
    {"id": "D02", "file": "app/files.py", "lines": [17, 17], "why_safe": "argument list, no shell, -- ends options"},
    {"id": "D03", "file": "app/crypto.py", "lines": [17, 17], "why_safe": "SHA-256 used as a checksum, not for passwords"},
    {"id": "D04", "file": "app/serialize.py", "lines": [15, 15], "why_safe": "yaml.safe_load builds plain data only"}
  ]
}
```
Each vuln has a **line range**, not one line: a scanner can report the SQL bug on the line that builds the query (5) *or* the line that runs it (6),
and both are correct. `scanner` records **which tool should catch it**, so Part B can say "missed because we don't run Checkov yet" instead of
"Sentinel is bad". Matching will use **file + line range**, not CWE, because different tools pick different CWE numbers for the same bug.

---

## 📚 Key concepts
- **Ground truth**: you can only measure accuracy on data where you already know the answer.
- **Recall (detection rate)** = planted vulns found ÷ planted vulns. **False positive rate** = decoys flagged ÷ decoys. You need both:
  flag everything and recall is 100%, but so is the false positive rate.
- **Data contamination**: the thing being tested must not see the answers (hints in names/comments, answer key inside the scanned folder).
- **Defense in depth, measured**: each scanner covers different bug classes. The `scanner` column shows which layer is missing today.

## 🔐 Security note
- A deliberately vulnerable folder in a public repo is normal (OWASP does it), **as long as it's never executed**. Nothing in `compose.yaml` or
  any Dockerfile of ours may point at `evals/`.
- Week 9 CI will run Trivy on *our* repo. Exclude `evals/` there, or the pipeline fails on our own exam.
- All "secrets" here are obviously fake. Never plant a real-looking credential, even a revoked one.

## ✅ Check it works
From the repo root:
```powershell
Get-ChildItem -Recurse evals\benchmark | Select-Object -ExpandProperty FullName
python -c "import json; d=json.load(open('evals/benchmark/expected.json')); print(len(d['vulns']), 'vulns,', len(d['decoys']), 'decoys')"
Select-String -Path evals\benchmark\target\app\*.py -Pattern "shell=True|pickle.loads|debug=True"
```
Expected: the folders `target` and `target\app`, 8 files inside them (6 `.py`, `Dockerfile`, `requirements.txt`) and `expected.json`, then `15 vulns, 4 decoys`, then exactly:
```
evals\benchmark\target\app\files.py:13:...shell=True...
evals\benchmark\target\app\serialize.py:7:...pickle.loads...
evals\benchmark\target\app\web.py:24:...debug=True...
```
(If a line number differs, a blank line is missing or extra in that file.)

Then a first **by-eye** run (the automatic grading is Part B):
```powershell
cd agents; .\.venv\Scripts\Activate.ps1
python -m sentinel scan ..\evals\benchmark\target
```
Count yourself how many of V01–V15 appear. Keep the output, because Part B will compute the same number automatically.

Commit:
```powershell
git add evals/benchmark; git commit -m "test(evals): benchmark target with 15 planted vulns, 4 decoys and answer key"
```

**Worth thinking about:** the triage LLM is allowed to mark findings as false positives. If it wrongly calls a *real* planted vuln a false positive,
should the score count that as "found" or "missed"? (Part B will need a rule.)

## ➡️ Next step
Part B: `evals/score.py` runs the scan, matches issues to the answer key by file + line range, and prints recall, false positives, and misses per scanner.
Tell Claude "I finished step 4.2 Part A, please review".
