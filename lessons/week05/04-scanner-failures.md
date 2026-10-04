# Week 5 · Step 5.2 Part C — One broken scanner doesn't kill the scan (but is never hidden)

## 🗺️ In plain words: what we're doing today

Today, if **one** scanner crashes (Docker hiccup, Semgrep can't download its rules, a 5-minute timeout), the **whole** scan dies. The
results the other scanners *did* produce are thrown away, and the PR gets no comment at all. With 4 scanners in 5.3, that happens
4 times as often. In this step a crashed scanner becomes a **line in the report** ("semgrep failed") while the other scanners' results
still get triaged and posted. The hard part is the security rule that comes with it: a scan with a missing scanner must **never look
clean**. No green ✅, no exit code 0.

**Example:** quit Docker Desktop and run the scan. Before this step you got one `scan failed` error and nothing else. After it you get
`sentinel: scanner gitleaks failed (RuntimeError), the report is incomplete` (and the same for semgrep), with **exit code 2**. On a PR, the comment starts with
`⚠️ Scan incomplete: semgrep failed, so this report may be missing issues.`

## 🎯 Goal

`run_scanner` catches its scanner's crash and records a `ScannerFailure` in the graph state (a second list with a reducer, like `findings`).
The CLI, the worker and the PR comment all show it, and an incomplete scan always fails CI. This closes step 5.2.

## 🧰 Tools in this step

No new tool. The one new idea is **graceful degradation**: a **car whose dashboard warns you "ABS failure" and still lets you drive**,
rather than a car that stops in the middle of the motorway, or one that hides the warning light. Many security tools get this wrong
in one direction or the other:

| Design | When semgrep crashes | Problem |
|---|---|---|
| Crash everything (today) | No report, PR has no comment | One flaky scanner = zero coverage. People learn to ignore the bot |
| Skip silently | Report shows only gitleaks results, "No issues ✅" | **Fail open**: the PR *looks* reviewed but wasn't. The worst option |
| **Degrade + flag (this step)** | gitleaks results posted + "Scan incomplete: semgrep failed", exit 2 | Partial value, honest about the gap |

```
plan ─► run_scanner(gitleaks) ── ok ─────► findings: [...] ──┐
   └──► run_scanner(semgrep) ─── crash ──► failures: [semgrep]┴─► triage ─► report + ⚠ "scan incomplete" + exit 2
```

## 🧩 Code, piece by piece

### 1. A failure is data
**Where:** `agents/sentinel/models.py`, at the bottom

```python
class ScannerFailure(BaseModel):
    scanner: str
    error: str
```
`error` holds only the **exception type** (`RuntimeError`, `TimeoutExpired`), never the message. Your `run_semgrep` puts the
**last 500 characters of stderr** into its message. On a PR that text could contain file paths from the worker's temp folder, Docker details, or a
line of the scanned code. All of it would end up in a public PR comment. That's CWE-209, information exposure through an error message.
The full message goes to **our logs** (piece 2), where only we can read it.

### 2. Catch the crash at the scanner boundary
**Where:** `agents/sentinel/graph.py`.

Change the models import to:
```python
from sentinel.models import Finding, ScannerFailure, TriagedIssue
```
In `class ScanState`, add under `findings`:
```python
    failures: Annotated[list[ScannerFailure], operator.add]
```
Replace the whole `run_scanner` function (this also fixes the `}` that ended up on its own line in Part B):
```python
def run_scanner(task: ScannerTask) -> dict:
    name = task["scanner"]
    try:
        return {"findings": SCANNERS[name].run(Path(task["path"]))}
    except Exception as e:
        log.exception("scanner %s failed", name)
        return {"failures": [ScannerFailure(scanner=name, error=type(e).__name__)]}
```
`except Exception` is normally a code smell. Here it's deliberate, because this is a **boundary**: whatever goes wrong inside one scanner (Docker missing,
bad JSON, `subprocess.TimeoutExpired`) must not take the other scanners down. It doesn't catch `KeyboardInterrupt`, which derives from
`BaseException`, so Ctrl+C still stops everything. `log.exception` writes the full traceback and message to the logs. `failures` uses the same
`operator.add` reducer as `findings`, so two scanners failing in parallel both get recorded instead of overwriting each other. I checked:
LangGraph returns `failures: []` when nothing fails, so `result["failures"]` always exists.

What still fails the whole scan: **triage** (`TriageError`, LLM down). That's intended. Without triage there's nothing to report, and the
worker's dead-letter queue from 3.4 handles it.

### 3. The CLI: an incomplete scan never passes
**Where:** `agents/sentinel/cli.py`, in `main`. Replace
```python
        findings, issues = result["findings"], result["issues"]
```
with
```python
        findings, issues, failures = result["findings"], result["issues"], result["failures"]
```
and replace the last line of `main` (`return exit_code(issues, args.fail_on)`) with
```python
    for failure in failures:
        print(f"sentinel: scanner {failure.scanner} failed ({failure.error}), the report is incomplete", file=sys.stderr)
    return EXIT_ERROR if failures else exit_code(issues, args.fail_on)
```
The report is still printed and the `-o` file still written, so you keep what the working scanners found. But the exit code is **2** ("tool problem"),
whatever was found. In CI, a scan where semgrep crashed and gitleaks found nothing would otherwise exit 0 and let the merge through.
The warnings go to **stderr**, so `--format json > report.json` stays valid JSON.

### 4. The PR: scan returns failures, worker passes them on
**Where:** `agents/sentinel/github/scan_pr.py`. Change the models import to
```python
from sentinel.models import ScannerFailure, TriagedIssue
```
and replace the end of the `def scan_pr(...)` signature and its last line:
```python
def scan_pr(repo: str, head_sha: str, installation_id: int, settings: Settings
            ) -> tuple[list[TriagedIssue], list[ScannerFailure]]:
```
```python
    with checkout_pr_head(repo, head_sha, token) as path:
        result = build_graph(build_router(settings)).invoke({"path": str(path)})
    return result["issues"], result["failures"]
```
**Where:** `agents/sentinel/worker.py`, in `process_one`. Replace `issues = scan_pr(` with `issues, failures = scan_pr(`, and replace the
`action = post_report(...)` line with
```python
        for failure in failures:
            logger.warning("%s#%d scanner %s failed (%s)", job.repo, job.pr, failure.scanner, failure.error)
        action = post_report(job.repo, job.pr, job.head_sha, job.installation_id, issues, finding_count, failures,
                             settings)
```
Returning a tuple makes callers handle `failures`: if a caller forgets to unpack it, the code crashes instead of silently dropping the
information. The `return` moved out of the `with` block because nothing after the scan needs the checkout. Now the temp folder is deleted before
we return.

### 5. The PR comment: a loud banner, never a ✅
**Where:** `agents/sentinel/github/comment.py`. Change the models import to
```python
from sentinel.models import ScannerFailure, TriagedIssue
```
Replace the start of `render_comment`, from `def render_comment` down to `lines.append("No issues found. ✅")`:
```python
def render_comment(issues: list[TriagedIssue], finding_count: int, head_sha: str,
                   failures: list[ScannerFailure] = ()) -> str:
    lines = [MARKER, f"## 🛡️ Sentinel security report for `{head_sha[:7]}`", ""]
    if failures:
        names = ", ".join(sorted(f.scanner for f in failures))
        lines += [f"> ⚠️ **Scan incomplete:** {md_escape(names, 200)} failed, so this report may be missing issues. "
                  "Re-run the scan before merging.", ""]
    if not issues:
        lines.append("No issues found by the scanners that ran." if failures else "No issues found. ✅")
```
In `post_report`, add `failures` to the signature and pass it on:
```python
def post_report(repo: str, pr: int, head_sha: str, installation_id: int,
                issues: list[TriagedIssue], finding_count: int, failures: list[ScannerFailure],
                settings: Settings) -> str:
```
```python
    return upsert_comment(token, repo, pr, render_comment(issues, finding_count, head_sha, failures), bot_login)
```
The banner is at the **top** because reviewers read the first lines. "No issues found. ✅" becomes "No issues found by the scanners that ran.",
which is true and still useful, but nobody would read it as "all clear". Scanner names come from our own registry and aren't attacker
text, but they still go through `md_escape`. It costs nothing, and the day someone adds a scanner named after a plugin, it's already safe.
`failures` defaults to `()` in `render_comment` so the existing comment tests keep working.

### 6. Tests
**Where:** `agents/tests/test_graph.py`. Change the models import to `from sentinel.models import Finding, ScannerFailure`, then
**replace** `test_a_crashing_scanner_fails_the_whole_scan` with:
```python
def test_a_crashing_scanner_is_reported_and_the_others_still_count(monkeypatch, seen):
    def boom(path):
        raise RuntimeError("scanner exploded in /tmp/secret-path")

    monkeypatch.setattr(graph, "SCANNERS", {"ok": everywhere(slow_scanner("ok", 1)), "bad": everywhere(boom)})
    result = graph.build_graph(router=None).invoke({"path": "."})
    assert [f.tool for f in seen[0]] == ["ok"]
    assert result["failures"] == [ScannerFailure(scanner="bad", error="RuntimeError")]
    assert "secret-path" not in result["failures"][0].model_dump_json()
```
The old test said "a crash fails everything". That was the 5.1 rule, and this step deliberately changes it, so the test changes with it. The last
line checks the CWE-209 point: the error message stays out of the result.

**Where:** `agents/tests/test_cli.py`. Replace the two imports from `sentinel` at the top with
```python
from sentinel import cli
from sentinel.cli import EXIT_ERROR, EXIT_ISSUES, EXIT_OK, exit_code, parse_args, render_json, render_text
from sentinel.models import Finding, ScannerFailure, TriagedIssue
```
and add at the bottom:
```python
def test_incomplete_scan_never_passes(monkeypatch, capsys):
    failure = ScannerFailure(scanner="semgrep", error="TimeoutExpired")

    class FakeGraph:
        def invoke(self, state):
            return {"findings": [], "issues": [], "failures": [failure]}

    monkeypatch.setattr(cli, "Settings", lambda: None)
    monkeypatch.setattr(cli, "build_router", lambda settings: None)
    monkeypatch.setattr(cli, "build_graph", lambda router: FakeGraph())
    assert cli.main(["scan", "."]) == EXIT_ERROR
    assert "scanner semgrep failed (TimeoutExpired)" in capsys.readouterr().err
```

**Where:** `agents/tests/test_comment.py`. Change the models import to `from sentinel.models import Finding, ScannerFailure, TriagedIssue`, then add at the bottom:
```python
def test_incomplete_scan_is_never_shown_as_clean():
    body = render_comment([], 0, "b" * 40, [ScannerFailure(scanner="semgrep", error="RuntimeError")])
    assert "Scan incomplete" in body and "semgrep" in body
    assert "✅" not in body
```

**Where:** `agents/tests/test_worker.py`. `scan_pr` now returns a pair, so the fakes must too. Under `from sentinel import worker`, add
`from sentinel.models import ScannerFailure`, then make three small replacements:
- in `test_job_is_scanned_then_removed`: `... or [])` → `... or ([], []))`
- in `test_jobs_are_first_in_first_out`: `... or [])` → `... or ([], []))`
- in `test_report_is_posted_after_scan`: `lambda *a: []` → `lambda *a: ([], [])`

and add at the bottom:
```python
def test_partial_scan_still_posts_the_failure(r, monkeypatch):
    failure = ScannerFailure(scanner="semgrep", error="TimeoutExpired")
    sent = []
    monkeypatch.setattr(worker, "scan_pr", lambda *a: ([], [failure]))
    monkeypatch.setattr(worker, "post_report", lambda *args: sent.append(args) or "created")
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert sent[0][6] == [failure]
    assert lengths(r) == (0, 0, 0)
```
`sent[0][6]` is the 7th argument of `post_report`, i.e. `failures`. `lengths == (0, 0, 0)` shows that a partial scan is a **finished job**,
not a dead letter. Re-running it wouldn't help if semgrep is broken, and the PR already got an honest comment.

## 📚 Key concepts

- **Fail open vs fail closed, revisited.** In 5.1 "fail closed" meant "crash everything". That's safe but brittle. The finer version is: **never
  claim more than you checked.** Partial results are fine. A partial result *presented as complete* is the bug. The same idea applies
  everywhere in security: an antivirus that couldn't update its signatures must say so, and a health check that couldn't reach the database must not say "OK".
- **Exit codes are a contract with CI.** 0 = checked and clean, 1 = checked and found issues, 2 = couldn't check properly. CI pipelines
  and branch protection rules (week 9) act on these numbers, not on the text you print.
- **Error messages leak (CWE-209).** Stack traces and stderr contain paths, versions and sometimes data. Show *what* failed to users, keep
  *why* in logs. [CWE-209](https://cwe.mitre.org/data/definitions/209.html)
- **Isolation boundaries.** Each scanner node is a small "blast radius": its failure is contained and recorded. Week 6's sandbox
  applies the same idea to the Fixer agent, with containers instead of `try/except`.

## 🔐 Security note

- **Denial of review:** an attacker who can make *one* scanner crash on purpose (e.g. a file that makes Semgrep time out) used to stop
  the whole review. Now they only remove that scanner, and the PR says so in a banner. A human must still notice it. In week 9, branch
  protection will block merging on an incomplete scan.
- **Worth thinking about:** should Sentinel retry a failed scanner once before reporting it? What does a retry cost (time, an attacker
  doubling your compute bill with a file that always times out), and what does it buy?

## ✅ Check it works

From `agents/` with the venv active:
```powershell
python -m pytest -q
```
Expected: `74 passed` (71 + 1 CLI + 1 comment + 1 worker; the graph test was replaced, not added).

Real failure: **quit Docker Desktop** (tray icon → Quit), wait until it's fully stopped, then:
```powershell
python -m sentinel scan ..\evals\benchmark\target; echo "exit code: $LASTEXITCODE"
```
Expected (no LLM call is made, since there's nothing to triage):
```
No issues found.
sentinel: scanner gitleaks failed (RuntimeError), the report is incomplete
sentinel: scanner semgrep failed (RuntimeError), the report is incomplete
exit code: 2
```
Add `-v` to see the full Docker error in the logs: it's there, and only there.

Start Docker Desktop again, wait until it's running, then run the regression proof:
```powershell
python -m sentinel scan ..\evals\benchmark\target -o ..\evals\results\report.json; echo "exit code: $LASTEXITCODE"
python ..\evals\score.py ..\evals\results\report.json
```
Expected: exit code `1` (high issues found, no failures), `detection 8/15`, `decoys flagged 0/4`.

Commit (from the project root):
```powershell
git add agents/sentinel agents/tests lessons PROGRESS.md
git commit -m "feat(agents): a failed scanner is reported (CLI exit 2, PR banner) instead of failing the whole scan"
```

## ➡️ Next step
This closes 5.2. Next is 5.3: Trivy (vulnerable dependencies, V15) and Checkov (Dockerfile/IaC, V14), each one a new `ScannerSpec`.
Tell Claude "I finished step 5.2 Part C, please review".
