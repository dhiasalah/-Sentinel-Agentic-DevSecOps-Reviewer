# Week 4 · Step 4.2 — Benchmark, Part B: the grader (`evals/score.py`)

## 🗺️ In plain words: what we're doing today

In Part A we wrote the exam (the fake app) and the answer key (`expected.json`). You then graded Sentinel **by eye**: 7 of 15 found.
Today we write a small **grading script** that does the same counting automatically, in under a second, every time. It reads Sentinel's
JSON report, compares each reported issue with the answer key using **file + line**, and prints a score card. It also checks *how well*
Sentinel described each bug, because "right line, wrong diagnosis" (SSTI called "XSS") is a real problem you've already seen.

**Example:** at the end you'll run one command and see:
```
detection       7/15 (47%)
right CWE       6/7
severity ok     5/7
decoys flagged  0/4
...
missed, by the scanner that should catch it:
  checkov   1: V14
  gitleaks  1: V04
  semgrep   5: V01 V02 V06 V07 V12
  trivy     1: V15
```

## 🎯 Goal

A repeatable score for Sentinel: `scan → report.json → score.py → numbers`. From now on, every change (new scanner in week 5, new
prompt, new model) is judged by **whether these numbers go up**, not by gut feeling. In week 10 the same script runs in CI.

## 🧰 Tools in this step

- **Evaluation harness (the "grader")**: like the teacher who marks the exam with the answer key. It solves "did my change make Sentinel
  better or worse?". It's written in **plain Python with no import from `sentinel`**, on purpose: the judge must not depend on
  the thing being judged. If a bug in Sentinel's models also lived in the grader, both would agree and the bug would be invisible. It comes back in
  week 10 (CI + detection rate on the README).
- **Precision/recall-style metrics**: **detection (recall)** = planted bugs found ÷ planted bugs. **Decoys flagged** = our
  false-positive measure. We add two **quality** metrics, **right CWE** and **severity ok**, because a bug found with the wrong
  label misleads the developer. [Precision and recall (Wikipedia)](https://en.wikipedia.org/wiki/Precision_and_recall)
- No new install: `argparse`, `json` and `re` are Python's standard library, and `pytest` is already in `agents/.venv`.

```
python -m sentinel scan target -o evals/results/report.json      (Sentinel = the student)
                                        │
                                        ▼
expected.json ──────────────► evals/score.py ──► score card  (the teacher, knows nothing about Sentinel's code)
```

---

## 🧠 Scoring rules (decided before writing code)

| Situation | Counts as | Why |
|---|---|---|
| An issue has a finding in the vuln's **file** and **line range** | **found** | Tools label the same bug with different CWEs, so location is the fair test |
| Found, but no finding carries one of the accepted CWEs | found, **wrong CWE** | That's the V10 case (SSTI labeled CWE-79 XSS) |
| Found, but the issue's severity is below the key's floor | found, **severity too low** | `debug=True` = remote code execution, so MEDIUM undersells it |
| Real vuln, and the AI marked **every** matching issue false positive | found, counted in **dismissed** | Our policy (2.3) still shows it, so it's found. But the AI was wrong, and we want to see that number |
| A decoy is hit by an issue the AI did **not** dismiss | **decoy flagged** | A dismissed decoy is the AI doing its job correctly |
| An issue matches no vuln and no decoy | **unplanned** | Not scored as wrong (it may be a real bug we didn't plant), but worth reading |

---

## 🧩 Code, piece by piece

### 1. Answer key v2: several accepted CWEs + a severity floor
**Where:** `evals/benchmark/expected.json`. Replace the whole `"vulns": [ ... ]` list (keep `"target"` and `"decoys"` as they are).
```json
  "vulns": [
    {"id": "V01", "file": "app/db.py", "lines": [5, 6], "cwes": ["CWE-89"], "severity": "high", "title": "SQL injection", "scanner": "semgrep"},
    {"id": "V02", "file": "app/files.py", "lines": [8, 8], "cwes": ["CWE-22", "CWE-73"], "severity": "high", "title": "Path traversal", "scanner": "semgrep"},
    {"id": "V03", "file": "app/files.py", "lines": [13, 13], "cwes": ["CWE-78"], "severity": "high", "title": "OS command injection", "scanner": "semgrep"},
    {"id": "V04", "file": "app/crypto.py", "lines": [5, 5], "cwes": ["CWE-798", "CWE-259", "CWE-321"], "severity": "high", "title": "Hardcoded secret", "scanner": "gitleaks"},
    {"id": "V05", "file": "app/crypto.py", "lines": [9, 9], "cwes": ["CWE-328", "CWE-327", "CWE-916"], "severity": "medium", "title": "Weak password hash (MD5)", "scanner": "semgrep"},
    {"id": "V06", "file": "app/crypto.py", "lines": [13, 13], "cwes": ["CWE-338", "CWE-330"], "severity": "medium", "title": "Insecure random token", "scanner": "semgrep"},
    {"id": "V07", "file": "app/serialize.py", "lines": [7, 7], "cwes": ["CWE-502"], "severity": "high", "title": "Unsafe pickle", "scanner": "semgrep"},
    {"id": "V08", "file": "app/serialize.py", "lines": [11, 11], "cwes": ["CWE-502"], "severity": "high", "title": "Unsafe YAML load", "scanner": "semgrep"},
    {"id": "V09", "file": "app/auth.py", "lines": [5, 5], "cwes": ["CWE-347", "CWE-287"], "severity": "high", "title": "JWT signature not verified", "scanner": "semgrep"},
    {"id": "V10", "file": "app/web.py", "lines": [10, 10], "cwes": ["CWE-1336", "CWE-94"], "severity": "high", "title": "Server-side template injection", "scanner": "semgrep"},
    {"id": "V11", "file": "app/web.py", "lines": [15, 15], "cwes": ["CWE-918"], "severity": "high", "title": "SSRF", "scanner": "semgrep"},
    {"id": "V12", "file": "app/web.py", "lines": [20, 20], "cwes": ["CWE-601"], "severity": "medium", "title": "Open redirect", "scanner": "semgrep"},
    {"id": "V13", "file": "app/web.py", "lines": [24, 24], "cwes": ["CWE-489", "CWE-215"], "severity": "high", "title": "Flask debug mode", "scanner": "semgrep"},
    {"id": "V14", "file": "Dockerfile", "lines": [1, 5], "cwes": ["CWE-250"], "severity": "medium", "title": "Container runs as root", "scanner": "checkov"},
    {"id": "V15", "file": "requirements.txt", "lines": [1, 3], "cwes": ["CWE-1395", "CWE-1104"], "severity": "high", "title": "Vulnerable dependencies", "scanner": "trivy"}
  ],
```
`cwe` becomes **`cwes`**, a list of *accepted* answers. CWE is a tree: MD5 for passwords is correctly described by CWE-328 (weak hash),
its parent CWE-327 (broken crypto), or CWE-916 (password hash too fast). A good exam accepts every correct answer and rejects the wrong
*kind* of answer. That's why V10 accepts CWE-1336/CWE-94 (template/code injection) but **not** CWE-79 (XSS): XSS runs in the victim's
browser, while SSTI runs on your server. `severity` is the **floor** (minimum) Sentinel should reach. Bugs that give code execution or
full account takeover are `high`. Weak crypto, the open redirect and the root container are `medium`.

### 2. Make the CLI write the report file itself
**Where:** `agents/sentinel/cli.py`, in `parse_args`, add under the `--fail-on` argument:
```python
    scan.add_argument("-o", "--output", type=Path, help="also write the JSON report to this file (UTF-8)")
```
**Where:** same file, in `main`, add **just before** the `print(render_json(issues) ...)` line:
```python
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_json(issues), encoding="utf-8")
```
Why not just `> report.json`? Look at `agents/report.json`, committed in 2.4: its first bytes are `FF FE`, so it's **UTF-16**, because
Windows PowerShell's `>` re-encodes whatever a program prints. On top of that, PowerShell decodes the output with the console code page,
which garbles characters like the `‑` in "Server‑Side". **Data files should be written by the program with an explicit encoding, not by the
shell.** The file is also written only after a successful scan, so a crash never leaves a half-written report.

### 3. The grader: loading and matching
**Where:** new file `evals/score.py`
```python
"""Grade a Sentinel JSON report against the benchmark answer key."""
import argparse
import json
import re
from pathlib import Path

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
CWE_ID = re.compile(r"CWE-\d+")
DEFAULT_KEY = Path(__file__).parent / "benchmark" / "expected.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def hits(issues: list[dict], item: dict) -> list[tuple[dict, dict]]:
    first, last = item["lines"]
    return [
        (issue, finding)
        for issue in issues
        for finding in issue["findings"]
        if finding["file"].replace("\\", "/") == item["file"] and first <= finding["line"] <= last
    ]
```
`hits` is the heart of the grader. For one answer-key entry, it returns every (issue, finding) pair that lands in the same file and line range.
Paths are normalised (`\` → `/`) so a Windows-style path can't cause a false "miss". `utf-8-sig` also accepts a UTF-8 file that starts
with a BOM (what `Out-File -Encoding utf8` produces), so the grader doesn't care how the file was saved. The grader reads plain dicts, not
Sentinel's pydantic models: it only depends on the **JSON contract**, so it can grade any tool that writes the same shape.

### 4. The grader: scoring one vuln, the decoys, and the leftovers
**Where:** `evals/score.py`, under `hits`
```python
def grade_vuln(vuln: dict, issues: list[dict]) -> dict:
    matched = hits(issues, vuln)
    got_cwes = {cwe for _, finding in matched for text in finding["cwe"] for cwe in CWE_ID.findall(text)}
    top = min((issue["severity"] for issue, _ in matched), key=SEVERITY_ORDER.index, default=None)
    return {
        **vuln,
        "found": bool(matched),
        "dismissed": bool(matched) and all(issue["false_positive"] for issue, _ in matched),
        "cwe_ok": bool(got_cwes & set(vuln["cwes"])),
        "severity_ok": top is not None and SEVERITY_ORDER.index(top) <= SEVERITY_ORDER.index(vuln["severity"]),
        "got_cwes": sorted(got_cwes),
        "got_severity": top,
    }


def decoy_flagged(decoy: dict, issues: list[dict]) -> bool:
    return any(not issue["false_positive"] for issue, _ in hits(issues, decoy))


def unplanned(issues: list[dict], key: dict) -> int:
    items = key["vulns"] + key["decoys"]
    return sum(1 for issue in issues if not any(hits([issue], item) for item in items))


def grade(key: dict, issues: list[dict]) -> dict:
    return {
        "vulns": [grade_vuln(vuln, issues) for vuln in key["vulns"]],
        "decoys": {decoy["id"]: decoy_flagged(decoy, issues) for decoy in key["decoys"]},
        "unplanned": unplanned(issues, key),
    }
```
Each function is one row of the rules table above. Semgrep writes CWEs as `"CWE-918: Server-Side Request Forgery (SSRF)"`, so `CWE_ID`
pulls out just the ID before comparing. `top` is the **most severe** severity among matching issues (`min`, because `critical` is index 0).
A vuln can be hit by two issues (on `web.py:24`, the `0.0.0.0` issue and the `debug=True` issue), and it's credited once. That's also
why `0.0.0.0` does **not** show up as "unplanned": line matching can't tell two bugs on the same line apart. This is a known limit of
line-based grading, so keep one planted bug per line when you add more.

### 5. The grader: the score card and the command line
**Where:** `evals/score.py`, under `grade`
```python
def render(result: dict) -> str:
    vulns, decoys = result["vulns"], result["decoys"]
    found = [r for r in vulns if r["found"]]
    lines = [
        f"detection       {len(found)}/{len(vulns)} ({len(found) / len(vulns):.0%})",
        f"right CWE       {sum(r['cwe_ok'] for r in found)}/{len(found)}",
        f"severity ok     {sum(r['severity_ok'] for r in found)}/{len(found)}",
        f"dismissed       {sum(r['dismissed'] for r in found)}  (real vulns the AI called false positive)",
        f"decoys flagged  {sum(decoys.values())}/{len(decoys)}  {' '.join(k for k, v in decoys.items() if v)}",
        f"unplanned       {result['unplanned']}  (issues that match no vuln and no decoy)",
        "",
        "found:",
    ]
    for r in found:
        problems = []
        if not r["cwe_ok"]:
            problems.append(f"got {'/'.join(r['got_cwes']) or 'none'} (want {'/'.join(r['cwes'])})")
        if not r["severity_ok"]:
            problems.append(f"severity {r['got_severity']} (want {r['severity']}+)")
        if r["dismissed"]:
            problems.append("AI called it a false positive")
        lines.append(f"  {r['id']} {r['title']:32} {'; '.join(problems) or 'ok'}")
    missed: dict[str, list[str]] = {}
    for r in vulns:
        if not r["found"]:
            missed.setdefault(r["scanner"], []).append(r["id"])
    lines.append("missed, by the scanner that should catch it:")
    for scanner, ids in sorted(missed.items()):
        lines.append(f"  {scanner:9} {len(ids)}: {' '.join(ids)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade a Sentinel JSON report against the benchmark answer key.")
    parser.add_argument("report", type=Path, help="output of: python -m sentinel scan <target> -o <report>")
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY, help="answer key (default: benchmark/expected.json)")
    args = parser.parse_args(argv)
    print(render(grade(load_json(args.key), load_json(args.report))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
`grade` computes the numbers and `render` turns them into text. They're kept separate so the tests check **numbers**, not formatting, and
week 10 can add a `--json` output for CI without touching the scoring. The "missed, by scanner" block is what turns 47% from "Sentinel is bad"
into a **roadmap**: 3 misses need week-5 scanners, and 5 are Semgrep blind spots.

### 6. Tests for the grader, and for the answer key
**Where:** new file `evals/test_score.py`
```python
from score import DEFAULT_KEY, decoy_flagged, grade, grade_vuln, load_json, unplanned

VULN = {"id": "V01", "file": "app/db.py", "lines": [5, 6], "cwes": ["CWE-89"], "severity": "high",
        "title": "SQL injection", "scanner": "semgrep"}
DECOY = {"id": "D01", "file": "app/db.py", "lines": [10, 10], "why_safe": "parameterised"}
KEY = {"vulns": [VULN], "decoys": [DECOY]}


def issue(file, line, severity="high", cwe="CWE-89: SQL Injection", false_positive=False):
    finding = {"tool": "semgrep", "rule_id": "r", "severity": "ERROR", "message": "m",
               "file": file, "line": line, "cwe": [cwe]}
    return {"title": "t", "severity": severity, "false_positive": false_positive,
            "explanation": "e", "fix": "f", "findings": [finding], "review_reasons": []}


def test_finding_anywhere_in_the_line_range_counts_even_with_windows_paths():
    result = grade_vuln(VULN, [issue("app\\db.py", 6)])
    assert result["found"] and result["cwe_ok"] and result["severity_ok"]


def test_wrong_line_or_wrong_file_is_a_miss():
    assert not grade_vuln(VULN, [issue("app/db.py", 7), issue("app/web.py", 5)])["found"]


def test_right_line_wrong_label_is_found_but_misdiagnosed():
    result = grade_vuln(VULN, [issue("app/db.py", 5, severity="medium", cwe="CWE-79: XSS")])
    assert result["found"]
    assert not result["cwe_ok"] and not result["severity_ok"]


def test_real_vuln_called_false_positive_is_found_but_dismissed():
    result = grade_vuln(VULN, [issue("app/db.py", 5, false_positive=True)])
    assert result["found"] and result["dismissed"]


def test_decoy_counts_as_flagged_only_if_the_ai_did_not_dismiss_it():
    assert decoy_flagged(DECOY, [issue("app/db.py", 10)])
    assert not decoy_flagged(DECOY, [issue("app/db.py", 10, false_positive=True)])


def test_issue_matching_nothing_is_unplanned():
    assert unplanned([issue("app/db.py", 5), issue("app/other.py", 1)], KEY) == 1


def test_empty_report_finds_nothing():
    result = grade(KEY, [])
    assert not result["vulns"][0]["found"] and result["decoys"] == {"D01": False}


def test_answer_key_points_at_real_lines_and_never_overlaps():
    key = load_json(DEFAULT_KEY)
    target = DEFAULT_KEY.parent / key["target"]
    seen = set()
    for item in key["vulns"] + key["decoys"]:
        first, last = item["lines"]
        line_count = len((target / item["file"]).read_text(encoding="utf-8").splitlines())
        assert 1 <= first <= last <= line_count, item["id"]
        spots = {(item["file"], n) for n in range(first, last + 1)}
        assert not spots & seen, f"{item['id']} overlaps another entry"
        seen |= spots
    for vuln in key["vulns"]:
        assert vuln["severity"] in {"critical", "high", "medium", "low", "info"}, vuln["id"]
        assert vuln["cwes"], vuln["id"]
```
The first seven tests pin down each rule from the table with tiny fake reports. The last one tests **the answer key itself**. A grader is only as
good as its key: if someone adds a blank line to `web.py`, every line number below it shifts, and the score silently drops. This test catches
that immediately. It also blocks two entries claiming the same line (a bug can't be both a vuln and a decoy).

### 7. Housekeeping: results are not source code
**Where:** root `.gitignore`, add at the bottom:
```
# Benchmark run outputs (regenerate, never commit)
evals/results/
```
Then remove the UTF-16 file from 2.4 (it's a scan output, not source):
```powershell
git rm agents/report.json
```
Reports change on every run, because LLM output varies. Committing them adds noise to `git diff` and can leak code snippets from whatever
was scanned. Week 10 will save the **scores** (small, comparable over time), not raw reports.

---

## 📚 Key concepts
- **Evaluation harness**: `data (target + key) → system under test → grader → metrics`. Every serious AI project has one. Without it, "we
  improved the prompt" means nothing. [OpenAI evals guide (same idea, general)](https://platform.openai.com/docs/guides/evals)
- **Detection is not enough**: the right line with the wrong diagnosis (V10) still misleads. Measure **quality of findings**, not just count.
- **Accept every correct answer**: CWEs form a tree, so a strict single-label key would punish correct but more general answers.
- **Test the answer key**: ground truth can have bugs too (line drift). A broken key gives confident, wrong numbers.
- **Judge independence**: the grader shares no code with Sentinel, only the JSON contract.
- **One run is one sample**: triage varies run to run (severity drift). In week 10 we'll run N times and report the average and spread.

## 🔐 Security note
- `score.py` only **reads** JSON and text. It never imports, executes or `eval`s anything from `target/`, which stays inert data.
- The report contains LLM-written text. The grader never interprets it, it only compares `file`, `line`, `cwe`, `severity`, `false_positive`.
  Only the structured fields affect the score, so a prompt injection hidden in `target/` can change the *words* but not the grading logic.
  (It could still change which issues the triage LLM *reports*, and that's exactly what the benchmark should reveal.)
- `evals/results/` is ignored, so scan outputs never end up in a public repo.

## ✅ Check it works
From `agents/` with the venv active:
```powershell
python -m pytest ..\evals\test_score.py -q
```
Expected:
```
........                                                                 [100%]
8 passed in 0.xxs
```
Then the whole Sentinel suite, to make sure the `-o` change broke nothing:
```powershell
python -m pytest -q
```
Expected: `52 passed`.

Then a real benchmark run (uses your Gemini/Groq quota once):
```powershell
python -m sentinel scan ..\evals\benchmark\target -o ..\evals\results\report.json
python ..\evals\score.py ..\evals\results\report.json
```
Expected, close to this (LLM output varies, especially severities):
```
detection       7/15 (47%)
right CWE       6/7
severity ok     5/7
dismissed       0  (real vulns the AI called false positive)
decoys flagged  0/4
unplanned       0  (issues that match no vuln and no decoy)

found:
  V03 OS command injection             ok
  V05 Weak password hash (MD5)         ok
  V08 Unsafe YAML load                 ok
  V09 JWT signature not verified       ok
  V10 Server-side template injection   got CWE-79 (want CWE-1336/CWE-94); severity medium (want high+)
  V11 SSRF                             ok
  V13 Flask debug mode                 severity medium (want high+)
missed, by the scanner that should catch it:
  checkov   1: V14
  gitleaks  1: V04
  semgrep   5: V01 V02 V06 V07 V12
  trivy     1: V15
```
Check the `-o` file is clean UTF-8 (not UTF-16):
```powershell
Format-Hex ..\evals\results\report.json | Select-Object -First 1
```
Expected: the first bytes are `5B 0D 0A` or `5B 0A` (`[` then a newline), **not** `FF FE`.

Commit:
```powershell
cd ..
git add evals/score.py evals/test_score.py evals/benchmark/expected.json agents/sentinel/cli.py .gitignore
git commit -m "test(evals): benchmark grader (detection, CWE, severity, decoys) + scan -o writes UTF-8 report"
```

**Worth thinking about:** if we now tweak the triage prompt until this benchmark shows 15/15, what have we actually learned about Sentinel on
*real* PRs? (Hint: search "Goodhart's law" and "overfitting to the test set". We'll come back to this in week 10 with a hidden second benchmark.)

## 🐛 What the first real run caught (fixed by Claude)
The first benchmark run **crashed** with `ClientError: 499 CANCELLED` from Gemini. `GeminiProvider` only treated `429` and `5xx` as
temporary, so `499` (Google cancelling the request on its side) was re-raised as a "real bug", the router **never tried Groq**, and the scan
exited with code 2. Fix in `agents/sentinel/llm/providers.py`: `if e.code in (408, 429, 499) or e.code >= 500:`, plus 6 tests in
`tests/test_router.py` (5 transient codes → fallback, `400` → still raised). Lessons: a fallback only protects you from the errors you
**classified**, so unknown codes should be looked up, not guessed. And the `-o` design paid off right away: because the scan failed, no report
was written, so the grader couldn't silently score an old one.

## ➡️ Next step
Record the first demo GIF (end of week 4). Tell Claude "I finished step 4.2 Part B, please review".
