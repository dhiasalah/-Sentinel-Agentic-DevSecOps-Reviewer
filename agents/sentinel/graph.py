import operator
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
import logging
from sentinel.llm.router import LLMRouter
from sentinel.models import Finding, ScannerFailure, TriagedIssue
from sentinel.planner import choose_scanners, list_files
from sentinel.scanners import gitleaks, semgrep
from sentinel.triage import triage

log = logging.getLogger(__name__)

Scanner = Callable[[Path], list[Finding]]


@dataclass(frozen=True)
class ScannerSpec:
    run: Scanner
    files: tuple[str, ...]


SCANNERS: dict[str, ScannerSpec] = {
    "gitleaks": ScannerSpec(
        run=lambda path: gitleaks.parse_findings(gitleaks.run_gitleaks(path)),
        files=("*",),
    ),
    "semgrep": ScannerSpec(
        run=lambda path: semgrep.parse_findings(semgrep.run_semgrep(path)),
        files=("*.py",),
    ),
}


class ScanState(TypedDict):
    path: str
    scanners: list[str]
    findings: Annotated[list[Finding], operator.add]
    failures: Annotated[list[ScannerFailure], operator.add]
    issues: list[TriagedIssue]


class ScannerTask(TypedDict):
    path: str
    scanner: str

def plan(state: ScanState) -> dict:
    files = list_files(Path(state["path"]))
    scanners = choose_scanners({name: spec.files for name, spec in SCANNERS.items()}, files)
    if files is None:
        log.warning("plan: repo too big or unreadable, running every scanner")
    log.info("plan: %s", scanners)
    return {"scanners": scanners}


def fan_out(state: ScanState) -> list[Send] | str:
    if not state["scanners"]:
        return "triage"
    return [Send("run_scanner", {"path": state["path"], "scanner": name}) for name in state["scanners"]]


def run_scanner(task: ScannerTask) -> dict:
    name = task["scanner"]
    try:
        return {"findings": SCANNERS[name].run(Path(task["path"]))}
    except Exception as e:
        log.exception("scanner %s failed", name)
        return {"failures": [ScannerFailure(scanner=name, error=type(e).__name__)]}


def build_graph(router: LLMRouter):
    def triage_node(state: ScanState) -> dict:
        findings = sorted(state["findings"], key=lambda f: (f.tool, f.file, f.line, f.rule_id))
        return {"issues": triage(findings, Path(state["path"]), router)}

    graph = StateGraph(ScanState)
    graph.add_node("plan", plan)
    graph.add_node("run_scanner", run_scanner)
    graph.add_node("triage", triage_node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", fan_out, ["run_scanner", "triage"])
    graph.add_edge("run_scanner", "triage")
    graph.add_edge("triage", END)
    return graph.compile()
