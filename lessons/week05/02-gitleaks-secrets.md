# Week 5 · Step 5.2 Part A — gitleaks: find hardcoded secrets (without leaking them ourselves)

## 🗺️ In plain words: what we're doing today

Sentinel can only find what its scanners find. Semgrep looks for dangerous *code*, but it can't tell that
`SECRET_KEY = "s3nt1nel-..."` is a password typed straight into the source. Today we add a second scanner,
**gitleaks**, whose only job is to spot secrets. We plug it into the graph from 5.1 as one new line in the registry,
and it runs **in parallel** with Semgrep. There's a twist. Once Sentinel finds a secret, Sentinel itself must not leak it:
not to the AI provider, and not into the PR comment. The repo being scanned must not be able to switch the scanner off either.

**Example:** the benchmark goes from `detection 7/15` to **`8/15`**, with V04 (hardcoded secret, `app/crypto.py:5`) newly found.
If you open the prompt sent to the LLM, line 5 reads `5: [hidden by Sentinel: possible secret]` instead of the real value.

## 🎯 Goal

`agents/sentinel/scanners/gitleaks.py` runs gitleaks in Docker (offline, pinned image, our own rules, secrets redacted).
`triage.py` masks secret lines before anything goes to the LLM.
Parts B (a planner that picks scanners from the files) and C (one failed scanner doesn't kill the scan) come next.

## 🧰 Tools in this step

- **gitleaks**: a **metal detector for passwords**. It reads every file and matches lines against ~200 rules ("looks like an AWS key",
  "looks like a GitHub token", "high-randomness string next to the word *secret*"). It solves the most common real-world breach:
  credentials committed to git. Bots scrape public GitHub for keys within minutes of a push, and git history keeps them forever, even after
  you delete the line. Sentinel needs it because Semgrep doesn't do this job (V04). It comes back in 5.4 as an MCP server and in week 9 as a
  CI step on Sentinel's own repo. [Docs](https://github.com/gitleaks/gitleaks)

```
                 ┌─► run_scanner(semgrep)  ── findings ─┐
START ─► plan ───┤                                      ├─► triage ─(lines with secrets hidden)─► LLM
                 └─► run_scanner(gitleaks) ── findings ─┘
                      docker: --network none, --redact, our config, repo can't silence it
```

## 🔍 What I found when I tested gitleaks on the benchmark (before writing this lesson)

These three results drive every design choice below:

| Test | Result | Consequence |
|---|---|---|
| gitleaks v8.24.0, **default rules**, on `evals/benchmark/target` | `no leaks found`. **V04 missed.** | Default rules are tuned for *few false alarms*. A readable secret like `s3nt1nel-benchmark-...` has too little randomness and contains ordinary words, so it's skipped. → we add **one custom rule**. |
| Same scan after adding a `.gitleaksignore` file with V04's fingerprint to the repo | `no leaks found` | **The scanned repo can silence the scanner.** An attacker's PR adds the file plus a secret, and Sentinel stays quiet. `--gitleaks-ignore-path` does *not* stop it: gitleaks always reads `.gitleaksignore` from the scanned folder. → we hide the repo's file behind an empty one. |
| A line ending in `# gitleaks:allow` | Hidden | Same attack, inline. → `--ignore-gitleaks-allow`. |

## 💻 Commands

Pull the exact image we'll pin (from the project root):
```powershell
docker pull zricethezav/gitleaks:v8.24.0
```
Expected (last line):
```
Digest: sha256:2bcceac45179b3a91bff11a824d0fb952585b429e54fc928728b1d4d5c3e5176
```

Create the folder for Sentinel's own gitleaks config, plus an empty file (its use is explained in piece 2):
```powershell
New-Item -ItemType Directory agents\sentinel\scanners\config
New-Item -ItemType File agents\sentinel\scanners\config\empty
```

## 🧩 Code, piece by piece

### 1. Our gitleaks rules
**Where:** new file `agents/sentinel/scanners/config/gitleaks.toml`

```toml
[extend]
useDefault = true

[[rules]]
id = "hardcoded-secret-assignment"
description = "Hardcoded secret assigned to a secret-looking variable"
regex = '''(?i)\b\w*(?:secret|passw(?:or)?d|api_?key|token)\w*\s*[:=]\s*["']([^"'\s]{8,})["']'''
secretGroup = 1
keywords = ["secret", "password", "passwd", "apikey", "api_key", "token"]
```
`useDefault = true` keeps all ~200 built-in rules and adds ours on top. The rule matches a **variable name containing
secret/password/api_key/token, assigned a quoted literal of 8+ characters**. `os.environ["SECRET_KEY"]` doesn't match, because the value isn't
a literal, and that's exactly the safe pattern we want developers to use. `secretGroup = 1` tells gitleaks which part is the secret, so
`--redact` replaces only the value. `keywords` is a speed filter: gitleaks only runs the regex on lines that contain one of these words.
The trade-off is that this rule *will* flag test fixtures like `password = "changeme123"`. That's acceptable: triage can mark a finding as a
false positive, and the policy from 2.3 then sends it to human review instead of dropping it.

### 2. Run gitleaks, locked down
**Where:** new file `agents/sentinel/scanners/gitleaks.py`

```python
import json
import subprocess
from pathlib import Path

from sentinel.models import Finding

GITLEAKS_IMAGE = "zricethezav/gitleaks:v8.24.0@sha256:2bcceac45179b3a91bff11a824d0fb952585b429e54fc928728b1d4d5c3e5176"
CONFIG_DIR = Path(__file__).parent / "config"


def run_gitleaks(target: Path) -> list[dict]:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {target}")
    mounts = ["-v", f"{target}:/src:ro", "-v", f"{CONFIG_DIR}:/config:ro"]
    repo_ignore = target / ".gitleaksignore"
    if repo_ignore.is_symlink() or (repo_ignore.exists() and not repo_ignore.is_file()):
        raise RuntimeError("refusing to scan: .gitleaksignore is not a regular file")
    if repo_ignore.exists():
        mounts += ["-v", f"{CONFIG_DIR / 'empty'}:/src/.gitleaksignore:ro"]
    cmd = [
        "docker", "run", "--rm", "--network", "none",
        *mounts,
        GITLEAKS_IMAGE,
        "dir", "/src",
        "--config", "/config/gitleaks.toml",
        "--ignore-gitleaks-allow",
        "--redact",
        "--no-banner", "--log-level", "error",
        "--report-format", "json", "--report-path", "-",
        "--exit-code", "0",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"gitleaks failed (exit {proc.returncode}): {proc.stderr[-500:]}")
    return json.loads(proc.stdout)
```
This follows the same shape as `run_semgrep`, with these additions, each one closing a hole:
- **Image pinned by digest** (`@sha256:...`). A tag like `v8.24.0` is just a label the publisher can move to different content. A digest is a fingerprint
  of the exact bytes, so a hijacked Docker Hub account can't swap in a malicious scanner. This is a supply-chain defense.
- **`--network none`**: a container that reads every secret in the repo has no internet access, so even a compromised image can't send them
  anywhere. (Semgrep can't do this yet: it downloads its `p/python` rules at runtime.)
- **`--config /config/gitleaks.toml`**: *our* rules, mounted read-only from Sentinel's code and never taken from the scanned repo.
- **Shadowing `.gitleaksignore`**: if the repo has one, we mount our empty file on top of it, so gitleaks reads an empty ignore list. We test the
  path from Python because Docker can't create a mount point inside a read-only mount. A **symlink or folder** named `.gitleaksignore` is
  refused outright: we don't try to predict what Docker would do with it, and failing closed is safer.
- **`--ignore-gitleaks-allow`**: inline `# gitleaks:allow` comments in the repo are ignored too.
- **`--redact`**: the report says `"Secret": "REDACTED"`, so the real value never even enters Sentinel's memory.
- **`--exit-code 0`**: by default gitleaks exits with `1` when it *finds* leaks. We want "found leaks" to be a normal result, so that any
  non-zero code really means "the scanner broke" and gets raised.

### 3. Turn the report into `Finding`s
**Where:** same file, `agents/sentinel/scanners/gitleaks.py`, at the bottom

```python
def parse_findings(raw: list[dict]) -> list[Finding]:
    return [
        Finding(
            tool="gitleaks",
            rule_id=leak["RuleID"],
            severity="ERROR",
            message=f"{leak['Description']} (value not shown)",
            file=leak["File"].removeprefix("/src/"),
            line=leak["StartLine"],
            end_line=leak["EndLine"],
            cwe=["CWE-798"],
        )
        for leak in raw
    ]
```
We copy only the *location* and the *rule*, never `Secret` or `Match`, even though they're already redacted. Two independent safety
measures are better than one. gitleaks has no severity, so every leak is `ERROR`, and the policy turns that into a **floor of HIGH**: the LLM
can't downgrade a leaked credential to "low". CWE-798 is "Use of Hard-coded Credentials".

### 4. Remember where a multi-line secret ends
**Where:** `agents/sentinel/models.py`, in `class Finding`, add after `cwe: list[str] = []`

```python
    end_line: int | None = None
```
A private key (`-----BEGIN RSA PRIVATE KEY-----`) spans about 25 lines. If we only knew the first line, we would hide line 1 and send the
other 24 to the LLM. The default `None` keeps every existing Semgrep finding and test working unchanged.

### 5. Hide secret lines from the LLM
**Where:** `agents/sentinel/triage.py`. Replace the whole `read_snippet` function, and add `secret_lines` right under it.

```python
def read_snippet(root: Path, file: str, line: int, context: int = 3,
                 hidden: frozenset[int] = frozenset()) -> str:
    root = root.resolve()
    path = (root / file).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"finding points outside the scanned repo: {file}")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(line - 1 - context, 0)
    end = min(line + context, len(lines))
    return "\n".join(
        f"{n}: [hidden by Sentinel: possible secret]" if n in hidden else f"{n}: {lines[n - 1]}"
        for n in range(start + 1, end + 1)
    )


def secret_lines(findings: list[Finding], file: str) -> frozenset[int]:
    return frozenset(
        n
        for f in findings
        if f.tool == "gitleaks" and f.file == file
        for n in range(f.line, (f.end_line or f.line) + 1)
    )
```
**Where:** in `build_prompt`, replace the `code:` line with

```python
            f"code:\n{read_snippet(root, f.file, f.line, hidden=secret_lines(findings, f.file))}\n"
```
The key detail is that `secret_lines` looks at **all** findings, not just the current one. Each snippet shows ±3 lines of context, so a
*Semgrep* finding on line 8 would happily print line 5, where the secret is. Masking by file and line across the whole batch closes that
side door. The LLM still sees the variable name in the surrounding lines plus the rule description, which is enough to explain the risk and
suggest "load it from an environment variable".

### 6. Register the scanner in the graph
**Where:** `agents/sentinel/graph.py`. Replace `from sentinel.scanners.semgrep import parse_findings, run_semgrep` with

```python
from sentinel.scanners import gitleaks, semgrep
```
and replace the `SCANNERS` dict with

```python
SCANNERS: dict[str, Scanner] = {
    "gitleaks": lambda path: gitleaks.parse_findings(gitleaks.run_gitleaks(path)),
    "semgrep": lambda path: semgrep.parse_findings(semgrep.run_semgrep(path)),
}
```
This is the payoff from 5.1: one line, and the new scanner runs in parallel. `plan`, `fan_out` and `triage` don't change. We import the
modules instead of the functions because both modules export a function called `parse_findings`.

### 7. Tests
**Where:** new file `agents/tests/test_gitleaks.py`

```python
import subprocess

import pytest

from sentinel.scanners import gitleaks
from sentinel.scanners.gitleaks import parse_findings, run_gitleaks

SAMPLE = [{
    "RuleID": "hardcoded-secret-assignment",
    "Description": "Hardcoded secret assigned to a secret-looking variable",
    "StartLine": 5,
    "EndLine": 5,
    "Match": 'SECRET_KEY = "REDACTED"',
    "Secret": "REDACTED",
    "File": "/src/app/crypto.py",
}]


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

    monkeypatch.setattr(gitleaks.subprocess, "run", fake_run)
    return calls


def test_parse_findings_keeps_location_and_drops_the_secret():
    [finding] = parse_findings(SAMPLE)
    assert finding.tool == "gitleaks"
    assert finding.file == "app/crypto.py"
    assert (finding.line, finding.end_line) == (5, 5)
    assert finding.cwe == ["CWE-798"]
    assert "REDACTED" not in finding.model_dump_json()


def test_scan_is_offline_redacted_and_ignores_inline_allows(tmp_path, captured):
    assert run_gitleaks(tmp_path) == []
    cmd = " ".join(captured[0])
    for flag in ("--network none", "--redact", "--ignore-gitleaks-allow", "--config /config/gitleaks.toml"):
        assert flag in cmd
    assert ".gitleaksignore" not in cmd


def test_repo_ignore_file_is_shadowed_by_an_empty_one(tmp_path, captured):
    (tmp_path / ".gitleaksignore").write_text("/src/app/crypto.py:hardcoded-secret-assignment:5\n")
    run_gitleaks(tmp_path)
    assert f"{gitleaks.CONFIG_DIR / 'empty'}:/src/.gitleaksignore:ro" in captured[0]


def test_refuses_a_gitleaksignore_that_is_not_a_plain_file(tmp_path, captured):
    (tmp_path / ".gitleaksignore").mkdir()
    with pytest.raises(RuntimeError, match="not a regular file"):
        run_gitleaks(tmp_path)
    assert captured == []
```
**Where:** `agents/tests/test_triage.py`, at the bottom

```python
def test_secret_lines_never_reach_the_llm(tmp_path):
    (tmp_path / "app.py").write_text('a = 1\nTOKEN = "hunter2hunter2"\nquery = f"SELECT {x}"\n')
    leak = Finding(tool="gitleaks", rule_id="secret", severity="ERROR", message="m",
                   file="app.py", line=2, end_line=2)
    prompt = build_prompt([leak, make_finding(line=3)], tmp_path, tag="abc123")
    assert "hunter2" not in prompt
    assert "SELECT" in prompt
```
The gitleaks tests check the **security flags** rather than gitleaks itself (it's faked). If someone later "cleans up" `--redact` or
`--network none`, a test fails loudly. The last two tests *are* the attacks from the table above, turned into regression tests. The triage
test reproduces the side door from piece 5: the secret is on line 2, but it's the Semgrep finding on line 3 whose context window would have
shown it.

## 📚 Key concepts

- **Secret scanning ≠ code scanning.** Semgrep asks "is this code dangerous?". gitleaks asks "is this text a credential?". They are different
  tools for different bug classes, which is why the roadmap runs several scanners in parallel instead of looking for one perfect tool.
- **Precision vs recall in rules.** gitleaks' defaults favour precision (few false alarms). That's right for a CI gate that blocks merges, and
  wrong for a reviewer that has an LLM plus a human to filter noise. Every security team ends up adding custom rules for its own code base.
- **Sensitive information disclosure (OWASP LLM02).** Whatever you put in a prompt goes to a third party (Gemini/Groq), may be logged there,
  and may come back in the model's answer, which then lands in a public PR comment. Masking *before* the prompt is the only reliable fix. You
  can't ask the model to "please don't repeat the secret". [OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/)
- **The target is untrusted, including its config files.** Any file in the scanned repo that changes the scanner's behaviour (`.gitleaksignore`,
  `.semgrepignore`, `nosemgrep` comments) is attacker input. This is the same idea as prompt injection from 2.3, applied to tools instead of the LLM.

## 🔐 Security note

- **If V04 were a real secret, finding it isn't enough: the secret has to be rotated.** Deleting the line doesn't remove it from git history.
  Sentinel's `fix` text should say "revoke and rotate", and that's worth checking in the PR comment.
- Semgrep has the same "repo can silence the scanner" problem: `# nosemgrep` comments and `.semgrepignore`. It's added to the blockers list. Fixing
  it needs Semgrep flags (`--disable-nosem`), so it's a good exercise for later.
- Semgrep's image (`semgrep/semgrep`) is still **unpinned** (latest). It's added to the same blocker as the unpinned Python requirements.

## ✅ Check it works

From `agents/` with the venv active:
```powershell
python -m pytest -q
```
Expected: `65 passed` (60 + 4 gitleaks + 1 triage).

gitleaks alone, on the benchmark:
```powershell
python -c "from pathlib import Path; from sentinel.scanners.gitleaks import run_gitleaks, parse_findings; print(parse_findings(run_gitleaks(Path('../evals/benchmark/target'))))"
```
Expected (one finding, no secret value anywhere):
```
[Finding(tool='gitleaks', rule_id='hardcoded-secret-assignment', severity='ERROR', message='Hardcoded secret assigned to a secret-looking variable (value not shown)', file='app/crypto.py', line=5, cwe=['CWE-798'], end_line=5)]
```

Full pipeline + benchmark (this also covers the regression proof skipped in 5.1):
```powershell
python -m sentinel scan ..\evals\benchmark\target -o ..\evals\results\report.json
python ..\evals\score.py ..\evals\results\report.json
```
Expected: `detection 8/15`, with **V04** now under `found`, `decoys flagged 0/4`, and `gitleaks` gone from the "missed, by scanner" list.
If it says `TriageError`, run it again (known blocker).

Search the report for the secret. It must not be there:
```powershell
Select-String -Path ..\evals\results\report.json -Pattern "s3nt1nel-benchmark"
```
Expected: **no output**.

Commit:
```powershell
cd ..
git add agents/sentinel/scanners/config agents/sentinel/scanners/gitleaks.py agents/sentinel/models.py agents/sentinel/triage.py agents/sentinel/graph.py agents/tests/test_gitleaks.py agents/tests/test_triage.py
git commit -m "feat(agents): gitleaks scanner node (pinned, offline, unsilenceable) + hide secret lines from the LLM"
```

**Worth thinking about:** we hide the secret from the LLM, but the PR comment still says "hardcoded secret in `app/crypto.py:5`" on a
**public** repo. Does that comment help an attacker find the secret faster than they would have anyway? What would you do differently for a
private repo vs a public one?

## ➡️ Next step
5.2 Part B: `plan` stops returning "every scanner" and picks them from the files present. Tell Claude "I finished step 5.2 Part A, please review".
