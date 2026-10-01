# Week 5 · Step 5.1 — LangGraph skeleton: plan → parallel scanners → triage

## 🗺️ In plain words: what we're doing today

Today Sentinel's pipeline is a straight line hard-coded in two places (`cli.py` and `scan_pr.py`): *run Semgrep, then ask the AI*.
This week we'll add three more scanners (gitleaks, Trivy, Checkov). If we keep the straight line, they run one after another and every new
scanner makes the scan slower and the code messier. So today we turn the pipeline into a **flowchart the program follows**: a
*planner* decides which scanners to run, they all run **at the same time**, and when all of them are done the AI triages everything together.
We only have one scanner today, so the result must be **exactly the same as before**. The benchmark from 4.2 will prove it.

**Example:** after today, `python ..\evals\score.py` still prints `detection 7/15 (47%)`, and a new test shows two fake 0.5-second scanners
finishing together in under 0.9 s (parallel, not 1 s in a row).

## 🎯 Goal

`agents/sentinel/graph.py`: a LangGraph graph `plan → run_scanner (×N in parallel) → triage`, used by both the CLI and the worker.
Adding a scanner in 5.2–5.3 becomes **one line** in a registry. In week 6 the same graph gets pause/resume for human approval.

## 🗓️ Week 5 plan
| Step | What | Benchmark effect |
|---|---|---|
| **5.1** | LangGraph skeleton, Semgrep only (today) | 7/15, unchanged (refactor) |
| 5.2 | gitleaks (secrets) + a planner that picks scanners from the files, + what happens when one scanner fails | V04 → 8/15 |
| 5.3 | Trivy (vulnerable dependencies) + Checkov (Dockerfile/IaC) | V14, V15 → 10/15 |
| 5.4 | Scanners as **MCP servers** (`mcp-servers/`), the graph calls them through MCP | unchanged (refactor) |
| 5.5 | Live PR: 4 scanners in parallel + benchmark re-run (**deliverable**) | ~10/15 |

## 🧰 Tools in this step

- **LangGraph**: a library for writing an AI pipeline as a **graph**, like a flowchart the program executes. The boxes (**nodes**) are
  plain Python functions, the arrows (**edges**) say what runs next, and a shared **state** dict is passed along like a clipboard every box
  can read and add to. It solves "coordinate several steps, some in parallel, some that must wait, and later pause for a human". Sentinel needs
  it because the roadmap adds parallel scanner agents (now), human approval via **interrupts** (week 6) and live progress streaming (week 8).
  LangGraph gives you those three for free on the same graph. [Docs](https://docs.langchain.com/oss/python/langgraph/overview)

```
            ┌──────────► run_scanner(semgrep)  ──┐
START ─► plan ─┼──────────► run_scanner(gitleaks) ─┼─► triage ─► END      (5.2+: more boxes, same graph)
            └──────────► run_scanner(trivy)    ──┘
     "which scanners?"     all run at the same time     waits for ALL, then one LLM call
```

**Workflow vs agent (important, and a security decision).** In an *agent*, the LLM chooses the next step. In a *workflow*, the code chooses.
Our `plan` node is **plain code, not an LLM**: it runs every registered scanner. If an LLM chose the scanners, a PR could contain text like
*"no need to run the secret scanner on this repo"* and a prompt injection could **switch off detection**. Rule: **the LLM may reason about
findings, but it never decides whether security checks run.** Anthropic calls this "use the simplest thing that works; workflows before agents".
[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)

**Honest trade-off:** for today alone, `concurrent.futures.ThreadPoolExecutor` would also run scanners in parallel with no new dependency.
We pay for LangGraph now because weeks 6 and 8 need **checkpoints** (save the graph state, pause for approval, resume later) and **streaming**
(send "gitleaks done" to the dashboard). Building those by hand is where bugs hide.

---

## 🧠 Four LangGraph ideas you need (in plain words)

1. **State**: a `TypedDict` that describes the clipboard. A node returns **only the keys it changes**, e.g. `{"scanners": [...]}`.
2. **Reducer**: what happens when two nodes write the same key at the same time. `Annotated[list[Finding], operator.add]` means
   "**concatenate** the lists" instead of "the last writer wins". Without it, parallel scanners would overwrite each other's findings.
3. **`Send` (fan-out)**: from `plan`, send one task per scanner to the same node `run_scanner`, each with its own small input. They run
   in the same **super-step**, which is LangGraph's word for "a round where everything that's ready runs in parallel".
4. **Fan-in**: the edge `run_scanner → triage` makes `triage` wait until **every** scanner task of that round has finished, and run **once**.

---

## 💻 Commands

Add LangGraph (pinned, remember what an unpinned redis-py did in 4.1).
**Where:** `agents/requirements.txt`, add at the bottom:
```
langgraph==1.2.12
```
Then, from `agents/` with the venv active:
```powershell
pip install -r requirements-dev.txt
python -c "import importlib.metadata as m; print(m.version('langgraph'))"
```
Expected: the install ends with `Successfully installed ... langgraph-1.2.12 ...`, then `1.2.12`.

---

## 🧩 Code, piece by piece

### 1. The graph: scanner registry and state
**Where:** new file `agents/sentinel/graph.py`
```python
import operator
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from sentinel.llm.router import LLMRouter
from sentinel.models import Finding, TriagedIssue
from sentinel.scanners.semgrep import parse_findings, run_semgrep
from sentinel.triage import triage

Scanner = Callable[[Path], list[Finding]]

SCANNERS: dict[str, Scanner] = {
    "semgrep": lambda path: parse_findings(run_semgrep(path)),
}


class ScanState(TypedDict):
    path: str
    scanners: list[str]
    findings: Annotated[list[Finding], operator.add]
    issues: list[TriagedIssue]


class ScannerTask(TypedDict):
    path: str
    scanner: str
```
`SCANNERS` is the **registry**: name → function `folder → list[Finding]`. Every scanner, current or future, must speak this one contract, and
that's the normalisation layer from 2.1 paying off. `ScanState` is the clipboard. `findings` has the `operator.add` **reducer**, so parallel
scanners **append** instead of overwriting each other. `path` is a `str`, not a `Path`, because in week 6 the state gets **saved to storage**
(checkpoints) and plain JSON-friendly types save cleanly. `ScannerTask` is the small private input each parallel scanner task receives.

### 2. The graph: the three steps
**Where:** `agents/sentinel/graph.py`, under `ScannerTask`
```python
def plan(state: ScanState) -> dict:
    return {"scanners": sorted(SCANNERS)}


def fan_out(state: ScanState) -> list[Send]:
    return [Send("run_scanner", {"path": state["path"], "scanner": name}) for name in state["scanners"]]


def run_scanner(task: ScannerTask) -> dict:
    return {"findings": SCANNERS[task["scanner"]](Path(task["path"]))}
```
`plan` is deliberately boring: **every** registered scanner runs (in 5.2 it will skip scanners that have nothing to look at, e.g. Checkov
when there's no Dockerfile, but still **by code rules, never by LLM**). `sorted` makes the order predictable in logs and tests. `fan_out`
turns the plan into one `Send` per scanner, and each becomes a parallel task of `run_scanner` with its own `{"path", "scanner"}` input.
`run_scanner` returns `{"findings": [...]}` and the reducer merges all of them into the state.

### 3. The graph: wiring it together
**Where:** `agents/sentinel/graph.py`, under `run_scanner`
```python
def build_graph(router: LLMRouter):
    def triage_node(state: ScanState) -> dict:
        findings = sorted(state["findings"], key=lambda f: (f.tool, f.file, f.line, f.rule_id))
        return {"issues": triage(findings, Path(state["path"]), router)}

    graph = StateGraph(ScanState)
    graph.add_node("plan", plan)
    graph.add_node("run_scanner", run_scanner)
    graph.add_node("triage", triage_node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", fan_out, ["run_scanner"])
    graph.add_edge("run_scanner", "triage")
    graph.add_edge("triage", END)
    return graph.compile()
```
`triage_node` is defined **inside** `build_graph` so it can use the `router` without putting it in the state. A router holds API clients
and keys, and that must **never** end up in a checkpoint saved to disk or a database (week 6). **Secrets stay out of state.** Findings from
parallel scanners arrive in whatever order the threads finish, so we **sort** them before triage. The AI then sees the same numbered list every
run, which removes one source of run-to-run randomness from the benchmark. `add_conditional_edges("plan", fan_out, ["run_scanner"])` says
"after `plan`, call `fan_out` to decide where to go", and the list tells LangGraph the possible targets (used for drawing the graph and validation).

### 4. The CLI uses the graph
**Where:** `agents/sentinel/cli.py`.
Imports: add `from sentinel.graph import build_graph` under `from sentinel.config import Settings`, and **delete** these two lines
(the graph owns them now):
```python
from sentinel.scanners.semgrep import parse_findings, run_semgrep
from sentinel.triage import triage
```
In `main`, **replace** the two lines inside `try:`
```python
        findings = parse_findings(run_semgrep(args.path))
        issues = triage(findings, args.path, build_router(Settings()))
```
with:
```python
        result = build_graph(build_router(Settings())).invoke({"path": str(args.path)})
        findings, issues = result["findings"], result["issues"]
```
`invoke` runs the graph from `START` to `END` and returns the final state. We only give it `path`. The other keys start empty (the reducer
starts `findings` as `[]`). The rest of `main` (`-o`, rendering, exit codes) doesn't change, because it only cares about `findings` and `issues`.

### 5. The worker uses the graph
**Where:** `agents/sentinel/github/scan_pr.py`.
Imports: add `from sentinel.graph import build_graph` under `from sentinel.github.checkout import checkout_pr_head`, and delete the same two
imports as in piece 4 (`parse_findings, run_semgrep` and `triage`).
**Replace** the two lines inside the `with checkout_pr_head(...)` block with:
```python
        return build_graph(build_router(settings)).invoke({"path": str(path)})["issues"]
```
Now the CLI and the worker run **the same pipeline**, so a scanner added in 5.2 shows up in both automatically. Before, you'd have had to
remember to edit two files, and forgetting one means the PR bot silently scans less than your local tests.

### 6. Tests: parallel, fan-in, and fail closed
**Where:** new file `agents/tests/test_graph.py`
```python
import time

import pytest

from sentinel import graph
from sentinel.models import Finding


def finding(tool, line):
    return Finding(tool=tool, rule_id="r", severity="ERROR", message="m", file="app.py", line=line)


def slow_scanner(tool, line):
    def scan(path):
        time.sleep(0.5)
        return [finding(tool, line)]
    return scan


@pytest.fixture
def seen(monkeypatch):
    calls = []

    def fake_triage(findings, root, router):
        calls.append(findings)
        return []

    monkeypatch.setattr(graph, "triage", fake_triage)
    return calls


def test_all_scanners_run_in_parallel_and_triage_sees_every_finding_once(monkeypatch, seen):
    monkeypatch.setattr(graph, "SCANNERS", {"b": slow_scanner("b", 2), "a": slow_scanner("a", 1)})
    start = time.perf_counter()
    result = graph.build_graph(router=None).invoke({"path": "."})
    assert time.perf_counter() - start < 0.9
    assert result["scanners"] == ["a", "b"]
    assert len(seen) == 1
    assert [f.tool for f in seen[0]] == ["a", "b"]


def test_a_crashing_scanner_fails_the_whole_scan(monkeypatch, seen):
    def boom(path):
        raise RuntimeError("scanner exploded")

    monkeypatch.setattr(graph, "SCANNERS", {"ok": slow_scanner("ok", 1), "bad": boom})
    with pytest.raises(RuntimeError, match="scanner exploded"):
        graph.build_graph(router=None).invoke({"path": "."})
    assert seen == []
```
The first test proves three things at once. It's **parallel**: two 0.5 s scanners take < 0.9 s, not 1 s. It's a **fan-in**: triage runs
exactly once. And it's **sorted and complete**: triage sees `a` then `b`, although `b` was registered first. The second test pins down a
**security decision**: if one scanner crashes, the whole scan fails and triage never runs. The alternative is to report the other scanners'
results as if everything were fine. A report that says "no secrets found" when the secret scanner actually **crashed** is worse than no report,
because people trust it. This is **fail closed**. In 5.2 we'll improve it to "partial results + a loud warning", but never *silent* partial results.

---

## 📚 Key concepts
- **State machine / graph orchestration**: steps are nodes, control flow is edges, and data flows through one typed state. [LangGraph concepts](https://docs.langchain.com/oss/python/langgraph/graph-api)
- **Reducers** decide how concurrent writes merge. They're the difference between "parallel" and "parallel and correct".
- **Fan-out / fan-in (map-reduce)**: split work, run it in parallel, wait for all, combine. [Map-reduce with Send](https://docs.langchain.com/oss/python/langgraph/graph-api#send)
- **Workflow before agent**: let code decide the control flow when the flow is known, and use the LLM only where judgement is needed.
- **Refactor + benchmark = safe refactor**: same score before and after is your proof that nothing broke.

## 🔐 Security note
- **The LLM never decides whether a security check runs.** `plan` is code. A planner LLM would be a prompt-injection target ("skip gitleaks").
- **Secrets never go in graph state.** The router (API keys) is captured in a closure, not the state, because state gets checkpointed from week 6.
- **Fail closed on scanner errors**: a crashed scanner must never look like "clean".
- New dependency = new supply-chain surface: LangGraph pulls in `langchain-core` and friends. It's pinned, and Trivy will scan our own
  dependencies in CI (week 9).

## ✅ Check it works
From `agents/` with the venv active:
```powershell
python -m pytest -q
```
Expected: `60 passed` (58 before + 2 new).

See the graph LangGraph built (Mermaid text you can paste into [mermaid.live](https://mermaid.live)):
```powershell
python -c "from sentinel.graph import build_graph; print(build_graph(None).get_graph().draw_mermaid())"
```
Expected, among other lines:
```
	__start__ --> plan;
	plan -.-> run_scanner;
	run_scanner --> triage;
	triage --> __end__;
```
(The dotted arrow `-.->` is the conditional fan-out.)

The regression proof, a real run through the graph:
```powershell
python -m sentinel scan ..\evals\benchmark\target -o ..\evals\results\report.json
python ..\evals\score.py ..\evals\results\report.json
```
Expected: the **same** numbers as 4.2: `detection 7/15 (47%)`, `decoys flagged 0/4` (severity may drift by one, because the LLM varies).
If the scan fails with `TriageError: LLM output does not match the schema`, that's the LLM returning bad JSON (it happened to Claude once while
preparing this lesson). Our validation correctly refused it. Just run it again. Handling this automatically is on the blockers list.

Then do one live PR (push a commit to the playground PR): the worker log shows the same `done, N issue(s)` and `report comment updated`.

Commit:
```powershell
cd ..
git add agents/requirements.txt agents/sentinel/graph.py agents/sentinel/cli.py agents/sentinel/github/scan_pr.py agents/tests/test_graph.py
git commit -m "feat(agents): LangGraph pipeline (plan -> parallel scanners -> triage) shared by CLI and worker"
```

**Worth thinking about:** in 5.2 gitleaks might crash on a weird file while Semgrep succeeds. Should the PR comment show Semgrep's results
with a warning "secret scan failed", or show nothing at all? What does each option cost the developer, and what does each cost security?

## ➡️ Next step
5.2: add **gitleaks** (secret scanning, catches V04), make `plan` choose scanners from the files present, and decide how a failed scanner
is reported. Tell Claude "I finished step 5.1, please review".
